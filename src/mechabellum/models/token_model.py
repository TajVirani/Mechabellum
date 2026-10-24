"""Saved token models: a TokenNet with its vocabulary, usable wherever a linear model artifact is."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..contracts import MatchSnapshot

TOKEN_ARTIFACT_SUFFIX = ".pt"


class TokenModel:
    def __init__(self, net: Any, vocabulary: Any) -> None:
        self.net = net
        self.vocabulary = vocabulary

    def win_probabilities(self, snapshots: Sequence[MatchSnapshot], perspectives: Sequence[int]) -> np.ndarray:
        """Probability that each row's perspective player wins."""
        import torch

        from .token_encoding import encode
        from .token_net import to_tensors

        own = to_tensors(encode(snapshots, perspectives, self.vocabulary))
        opponent = to_tensors(encode(snapshots, [1 - perspective for perspective in perspectives], self.vocabulary))
        self.net.eval()
        with torch.no_grad():
            return torch.sigmoid(self.net(own, opponent)).numpy().astype(np.float64)


def save_token_artifact(path: Path, model: TokenModel, metadata: dict[str, Any]) -> None:
    import torch

    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            **metadata,
            "kind": "token",
            "config": model.net.config.to_dict(),
            "vocabulary": model.vocabulary.to_dict(),
            "state": model.net.state_dict(),
        },
        path,
    )


def load_token_artifact(path: Path) -> dict[str, Any]:
    import torch

    from .token_encoding import Vocabulary
    from .token_net import TokenNet, TokenNetConfig

    stored = torch.load(path, map_location="cpu", weights_only=True)
    vocabulary = Vocabulary.from_dict(stored["vocabulary"])
    net = TokenNet(TokenNetConfig(**stored["config"]), vocabulary)
    net.load_state_dict(stored["state"])
    return {**stored, "model": TokenModel(net, vocabulary)}
