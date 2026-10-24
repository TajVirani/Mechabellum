"""Token models over unit formations (requires the `deep` extra: torch).

All three architectures score one perspective of a position; the win probability of the perspective player is
sigmoid(score(own view) - score(opponent view)), so the two players' probabilities always sum to one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import torch
from torch import nn

from .token_encoding import PAD, PLAYER_BAGS, TOKEN_NUMERIC, EncodedBatch, Vocabulary

Architecture = Literal["deepsets", "transformer", "gnn"]


@dataclass(frozen=True)
class TokenNetConfig:
    architecture: Architecture
    feature_count: int
    width: int = 64
    layers: int = 2
    heads: int = 4
    neighbours: int = 8
    dropout: float = 0.1

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def to_tensors(batch: EncodedBatch) -> dict[str, torch.Tensor]:
    tensors = {
        "unit": torch.from_numpy(batch.unit),
        "technologies": torch.from_numpy(batch.technologies),
        "equipment": torch.from_numpy(batch.equipment),
        "numeric": torch.from_numpy(batch.numeric),
        "mask": torch.from_numpy(batch.mask),
        "context_ids": torch.from_numpy(batch.context_ids),
        "context_features": torch.from_numpy(batch.context_features),
    }
    tensors.update({f"bag_{name}": torch.from_numpy(values) for name, values in batch.bags.items()})
    return tensors


class _BagEmbedding(nn.Module):
    """Mean of the embeddings of non-padding ids along the last axis."""

    def __init__(self, size: int, width: int) -> None:
        super().__init__()
        self.embedding = nn.Embedding(size, width, padding_idx=PAD)

    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        present = (ids != PAD).float().unsqueeze(-1)
        return (self.embedding(ids) * present).sum(-2) / present.sum(-2).clamp(min=1.0)


def _masked_mean(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    weights = mask.float().unsqueeze(-1)
    return (values * weights).sum(1) / weights.sum(1).clamp(min=1.0)


class TokenNet(nn.Module):
    def __init__(self, config: TokenNetConfig, vocabulary: Vocabulary) -> None:
        super().__init__()
        self.config = config
        width = config.width
        self.unit = nn.Embedding(vocabulary.size("unit"), width, padding_idx=PAD)
        self.technologies = _BagEmbedding(vocabulary.size("technology"), width)
        self.equipment = _BagEmbedding(vocabulary.size("equipment"), width)
        self.numeric = nn.Linear(TOKEN_NUMERIC, width)
        self.side = nn.Embedding(2, width)
        self.bags = nn.ModuleDict({name: _BagEmbedding(vocabulary.size(name), width) for name in PLAYER_BAGS})
        self.context_ids = nn.ModuleList(
            nn.Embedding(vocabulary.size(name), width) for name in ("map", "mode", "version")
        )
        self.context_features = nn.Sequential(
            nn.LayerNorm(config.feature_count), nn.Linear(config.feature_count, width)
        )
        if config.architecture == "deepsets":
            self.phi = nn.Sequential(nn.Linear(width, width), nn.GELU(), nn.Linear(width, width))
        elif config.architecture == "transformer":
            layer = nn.TransformerEncoderLayer(
                width, config.heads, dim_feedforward=2 * width, dropout=config.dropout, batch_first=True
            )
            self.encoder = nn.TransformerEncoder(layer, config.layers, enable_nested_tensor=False)
        elif config.architecture == "gnn":
            self.messages = nn.ModuleList(
                nn.Sequential(nn.Linear(2 * width + 3, width), nn.GELU(), nn.Linear(width, width))
                for _ in range(config.layers)
            )
            self.updates = nn.ModuleList(nn.LayerNorm(width) for _ in range(config.layers))
        else:
            raise ValueError(f"Unknown architecture: {config.architecture}")
        pooled = 4 * width  # own pool, opponent pool, own bags, opponent bags
        self.head = nn.Sequential(
            nn.Linear(pooled + 2 * width, width),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(width, 1),
        )
        # Auxiliary head for the next fight's advantage; trained only when the advantage loss weight is above 0.
        self.advantage_head = nn.Sequential(
            nn.Linear(pooled + 2 * width, width),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(width, 1),
        )

    def _tokens(self, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        side = batch["numeric"][..., 0].long()
        return (
            self.unit(batch["unit"])
            + self.technologies(batch["technologies"])
            + self.equipment(batch["equipment"])
            + self.numeric(batch["numeric"])
            + self.side(side)
        )

    def _mix(self, tokens: torch.Tensor, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        mask = batch["mask"]
        if self.config.architecture == "deepsets":
            return self.phi(tokens)
        if self.config.architecture == "transformer":
            # Attention runs across both armies, so a formation can weigh the opposing formations it faces.
            empty = ~mask.any(1)
            padding = ~mask
            padding[empty, 0] = False
            return self.encoder(tokens, src_key_padding_mask=padding)
        return self._message_passing(tokens, batch)

    def _message_passing(self, tokens: torch.Tensor, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        """k-nearest-neighbour graph over the board; edges carry the relative position and whether sides match."""
        mask = batch["mask"]
        numeric = batch["numeric"]
        side = numeric[..., 0]
        # Board position in the perspective frame: own half has y < 0, the opponent's y > 0.
        x = numeric[..., 4]
        y = torch.where(side > 0.5, numeric[..., 5], -numeric[..., 5])
        position = torch.stack([x, y], -1)
        distance = torch.cdist(position, position)
        invalid = ~(mask.unsqueeze(1) & mask.unsqueeze(2))
        distance = distance.masked_fill(invalid, float("inf"))
        distance.diagonal(dim1=1, dim2=2).fill_(float("inf"))
        k = min(self.config.neighbours, tokens.shape[1] - 1)
        nearest = distance.topk(k, dim=-1, largest=False)
        valid = torch.isfinite(nearest.values).unsqueeze(-1).float()
        index = nearest.indices
        relative = torch.gather(
            position.unsqueeze(1).expand(-1, tokens.shape[1], -1, -1), 2, index.unsqueeze(-1).expand(-1, -1, -1, 2)
        ) - position.unsqueeze(2)
        neighbour_side = torch.gather(side.unsqueeze(1).expand(-1, tokens.shape[1], -1), 2, index)
        same_side = (neighbour_side == side.unsqueeze(-1)).float().unsqueeze(-1)
        state = tokens
        for message, update in zip(self.messages, self.updates, strict=True):
            neighbours = torch.gather(
                state.unsqueeze(1).expand(-1, state.shape[1], -1, -1),
                2,
                index.unsqueeze(-1).expand(-1, -1, -1, state.shape[-1]),
            )
            own = state.unsqueeze(2).expand_as(neighbours)
            messages = message(torch.cat([own, neighbours, relative, same_side], -1)) * valid
            state = update(state + messages.sum(2) / valid.sum(2).clamp(min=1.0))
        return state

    def score(self, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        return self.head(self.representation(batch)).squeeze(-1)

    def representation(self, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        mixed = self._mix(self._tokens(batch), batch)
        mask = batch["mask"]
        side = batch["numeric"][..., 0]
        own = _masked_mean(mixed, mask & (side < 0.5))
        opponent = _masked_mean(mixed, mask & (side > 0.5))
        bags = [self.bags[name](batch[f"bag_{name}"]) for name in PLAYER_BAGS]  # each (n, 2, width)
        own_bags = torch.stack([bag[:, 0] for bag in bags]).mean(0)
        opponent_bags = torch.stack([bag[:, 1] for bag in bags]).mean(0)
        context = sum(embedding(batch["context_ids"][:, index]) for index, embedding in enumerate(self.context_ids))
        features = self.context_features(batch["context_features"])
        return torch.cat([own, opponent, own_bags, opponent_bags, context, features], -1)

    def forward(self, own_view: dict[str, torch.Tensor], opponent_view: dict[str, torch.Tensor]) -> torch.Tensor:
        """Logit that the perspective player of `own_view` wins; antisymmetric by construction."""
        return self.score(own_view) - self.score(opponent_view)

    def heads(
        self, own_view: dict[str, torch.Tensor], opponent_view: dict[str, torch.Tensor]
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Win logit and predicted next-fight advantage in [-1, 1], both antisymmetric in the two views."""
        own, opponent = self.representation(own_view), self.representation(opponent_view)
        logit = (self.head(own) - self.head(opponent)).squeeze(-1)
        advantage = torch.tanh(self.advantage_head(own) - self.advantage_head(opponent)).squeeze(-1)
        return logit, advantage
