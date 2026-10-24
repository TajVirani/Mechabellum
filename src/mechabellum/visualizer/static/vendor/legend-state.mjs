// src/is.ts
var hasOwnProperty = Object.prototype.hasOwnProperty;
function isArray(obj) {
  return Array.isArray(obj);
}
function isString(obj) {
  return typeof obj === "string";
}
function isObject(obj) {
  return !!obj && typeof obj === "object" && !(obj instanceof Date) && !isTemporal(obj) && !isArray(obj);
}
function isPlainObject(obj) {
  return isObject(obj) && obj.constructor === Object;
}
function isFunction(obj) {
  return typeof obj === "function";
}
function isPrimitive(arg) {
  const type = typeof arg;
  return arg !== void 0 && (isDate(arg) || isTemporal(arg) || type !== "object" && type !== "function");
}
function isDate(obj) {
  return obj instanceof Date;
}
function isTemporal(obj) {
  return !!obj && (typeof obj === "object" || typeof obj === "function") && typeof obj[Symbol.toStringTag] === "string" && obj[Symbol.toStringTag].startsWith("Temporal.");
}
function isSymbol(obj) {
  return typeof obj === "symbol";
}
function isBoolean(obj) {
  return typeof obj === "boolean";
}
function isPromise(obj) {
  return obj instanceof Promise;
}
function isMap(obj) {
  return obj instanceof Map || obj instanceof WeakMap;
}
function isSet(obj) {
  return obj instanceof Set || obj instanceof WeakSet;
}
function isNumber(obj) {
  const n = obj;
  return typeof n === "number" && n - n < 1;
}
function isEmpty(obj) {
  if (!obj)
    return false;
  if (isArray(obj))
    return obj.length === 0;
  if (isMap(obj) || isSet(obj))
    return obj.size === 0;
  for (const key in obj) {
    if (hasOwnProperty.call(obj, key)) {
      return false;
    }
  }
  return true;
}
function isNullOrUndefined(value) {
  return value === void 0 || value === null;
}
var setPrimitives = /* @__PURE__ */ new Set(["boolean", "string", "number"]);
function isActualPrimitive(arg) {
  return setPrimitives.has(typeof arg);
}
function isChildNode(node) {
  return !!node.parent;
}

// src/globals.ts
var symbolToPrimitive = Symbol.toPrimitive;
var symbolIterator = Symbol.iterator;
var symbolGetNode = Symbol("getNode");
var symbolDelete = /* @__PURE__ */ Symbol("delete");
var symbolOpaque = Symbol("opaque");
var symbolPlain = Symbol("plain");
var optimized = Symbol("optimized");
var symbolLinked = Symbol("linked");
var globalState = {
  pendingNodes: /* @__PURE__ */ new Map(),
  dirtyNodes: /* @__PURE__ */ new Set()
};
function isHintOpaque(value) {
  return value && (value[symbolOpaque] || value["$$typeof"]);
}
function isHintPlain(value) {
  return value && value[symbolPlain];
}
function getPathType(value) {
  return isArray(value) ? "array" : isMap(value) ? "map" : value instanceof Set ? "set" : "object";
}
function replacer(key, value) {
  if (isMap(value)) {
    return {
      __LSType: "Map",
      value: Array.from(value.entries())
      // or with spread: value: [...value]
    };
  } else if (value instanceof Set) {
    return {
      __LSType: "Set",
      value: Array.from(value)
      // or with spread: value: [...value]
    };
  } else if (globalState.replacer) {
    value = globalState.replacer(key, value);
  }
  return value;
}
var ISO8601 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{3}Z$/;
function reviver(key, value) {
  if (value) {
    if (typeof value === "string" && ISO8601.test(value)) {
      return new Date(value);
    }
    if (typeof value === "object") {
      if (value.__LSType === "Map") {
        return new Map(value.value);
      } else if (value.__LSType === "Set") {
        return new Set(value.value);
      }
    }
    if (globalState.reviver) {
      value = globalState.reviver(key, value);
    }
  }
  return value;
}
function safeStringify(value) {
  return value ? JSON.stringify(value, replacer) : value;
}
function safeParse(value) {
  return value ? JSON.parse(value, reviver) : value;
}
function clone(value) {
  return safeParse(safeStringify(value));
}
function isObservable(value$) {
  return !!value$ && !!value$[symbolGetNode];
}
function getNode(value$) {
  return value$ && value$[symbolGetNode];
}
function isEvent(value$) {
  var _a;
  return value$ && ((_a = value$[symbolGetNode]) == null ? void 0 : _a.isEvent);
}
function setNewValue(parentValue, key, newValue, useSetFn, useMapFn) {
  if (useSetFn) {
    parentValue.add(newValue);
  } else if (useMapFn) {
    parentValue.set(key, newValue);
  } else {
    parentValue[key] = newValue;
  }
  return newValue;
}
function setNodeValue(node, newValue) {
  var _a;
  const parentNode = (_a = node.parent) != null ? _a : node;
  const key = node.parent ? node.key : "_";
  const isDelete = newValue === symbolDelete;
  if (isDelete)
    newValue = void 0;
  const parentValue = node.parent ? ensureNodeValue(parentNode) : parentNode.root;
  const useSetFn = isSet(parentValue);
  const useMapFn = isMap(parentValue);
  const parentHadKey = useSetFn || useMapFn ? parentValue.has(key) : Object.prototype.hasOwnProperty.call(parentValue, key);
  const prevValue = useSetFn ? key : useMapFn ? parentValue.get(key) : parentValue[key];
  const isFunc = isFunction(newValue);
  newValue = !parentNode.isAssigning && isFunc && !isFunction(prevValue) ? newValue(prevValue) : newValue;
  if (newValue !== prevValue) {
    try {
      parentNode.isSetting = (parentNode.isSetting || 0) + 1;
      if (isDelete) {
        if (useMapFn || useSetFn) {
          parentValue.delete(key);
        } else {
          delete parentValue[key];
        }
      } else {
        setNewValue(parentValue, key, newValue, useSetFn, useMapFn);
      }
    } finally {
      parentNode.isSetting--;
    }
  }
  const parentHasKey = useSetFn || useMapFn ? parentValue.has(key) : Object.prototype.hasOwnProperty.call(parentValue, key);
  return { prevValue, newValue, parentValue, parentHadKey, parentHasKey };
}
var arrNodeKeys = [];
function getNodeValue(node) {
  let count = 0;
  let n = node;
  while (isChildNode(n)) {
    arrNodeKeys[count++] = n.key;
    n = n.parent;
  }
  let child = node.root._;
  for (let i = count - 1; child && i >= 0; i--) {
    const key = arrNodeKeys[i];
    child = key !== "size" && isMap(child) ? child.get(key) : child[key];
  }
  return child;
}
function getChildNode(node, key, asFunction) {
  var _a, _b;
  let child = (_a = node.children) == null ? void 0 : _a.get(key);
  if (!child) {
    child = {
      root: node.root,
      parent: node,
      key,
      lazy: true,
      numListenersRecursive: 0
    };
    if (((_b = node.lazyFn) == null ? void 0 : _b.length) === 1) {
      asFunction = node.lazyFn.bind(node, key);
    }
    if (isFunction(asFunction)) {
      child = Object.assign(() => {
      }, child);
      child.lazyFn = asFunction;
    }
    if (!node.children) {
      node.children = /* @__PURE__ */ new Map();
    }
    node.children.set(key, child);
  }
  return child;
}
function ensureNodeValue(node) {
  let value = getNodeValue(node);
  if (!value || isFunction(value)) {
    if (isChildNode(node)) {
      const parent = ensureNodeValue(node.parent);
      const useSetFn = isSet(parent);
      const useMapFn = isMap(parent);
      value = setNewValue(parent, node.key, {}, useSetFn, useMapFn);
    } else {
      value = node.root._ = {};
    }
  }
  return value;
}
function findIDKey(obj, node) {
  var _a, _b;
  let idKey = isObservable(obj) ? void 0 : isObject(obj) ? "id" in obj ? "id" : "key" in obj ? "key" : "_id" in obj ? "_id" : "__id" in obj ? "__id" : void 0 : void 0;
  if (!idKey && node.parent) {
    const k = node.key + "_keyExtractor";
    const keyExtractor = (_b = (_a = node.functions) == null ? void 0 : _a.get(k)) != null ? _b : getNodeValue(node.parent)[node.key + "_keyExtractor"];
    if (keyExtractor && isFunction(keyExtractor)) {
      idKey = keyExtractor;
    }
  }
  return idKey;
}
function extractFunction(node, key, fnOrComputed) {
  if (!node.functions) {
    node.functions = /* @__PURE__ */ new Map();
  }
  node.functions.set(key, fnOrComputed);
}
function equals(a, b) {
  return a === b || isDate(a) && isDate(b) && +a === +b || isTemporal(a) && isTemporal(b) && String(a) === String(b);
}
function getKeys(obj, isArr, isMap2, isSet2) {
  return isArr ? void 0 : obj ? isSet2 ? Array.from(obj) : isMap2 ? Array.from(obj.keys()) : Object.keys(obj) : [];
}

// src/ObservableHint.ts
function addSymbol(value, symbol) {
  if (value) {
    Object.defineProperty(value, symbol, {
      value: true,
      enumerable: false,
      writable: true,
      configurable: true
    });
  }
  return value;
}
var ObservableHint = {
  opaque: function opaqueObject(value) {
    return addSymbol(value, symbolOpaque);
  },
  plain: function plainObject(value) {
    return addSymbol(value, symbolPlain);
  },
  function: function plainObject2(value) {
    return addSymbol(value, symbolPlain);
  }
};

// src/checkPlain.ts
function checkPlain(node, value) {
  var _a;
  if (!node.isPlain && (((_a = node.parent) == null ? void 0 : _a.isPlain) || isHintPlain(value))) {
    node.isPlain = true;
  }
}

// src/helpers.ts
function computeSelector(selector, getOptions, e, retainObservable) {
  let c = selector;
  if (!isObservable(c) && isFunction(c)) {
    c = e ? c(e) : c();
  }
  return isObservable(c) && !retainObservable ? c.get(getOptions) : c;
}
function getObservableIndex(value$) {
  const node = getNode(value$);
  const n = +node.key;
  return isNumber(n) ? n : -1;
}
function opaqueObject2(value) {
  if (process.env.NODE_ENV === "development") {
    console.warn("[legend-state]: In version 3.0 opaqueObject is moved to ObservableHint.opaque");
  }
  if (value) {
    value[symbolOpaque] = true;
  }
  return value;
}
var getValueAtPathReducer = (o, p) => o && o[p];
function getValueAtPath(obj, path) {
  return path.reduce(getValueAtPathReducer, obj);
}
function setAtPath(obj, path, pathTypes, value, mode, fullObj, restore) {
  let p = void 0;
  let o = obj;
  if (path.length > 0) {
    let oFull = fullObj;
    for (let i = 0; i < path.length; i++) {
      p = path[i];
      const map = isMap(o);
      let child = o ? map ? o.get(p) : o[p] : void 0;
      const fullChild = oFull ? map ? oFull.get(p) : oFull[p] : void 0;
      if (child === symbolDelete) {
        if (oFull) {
          if (map) {
            o.set(p, fullChild);
          } else {
            o[p] = fullChild;
          }
          restore == null ? void 0 : restore(path.slice(0, i + 1), fullChild);
        }
        return obj;
      } else if (child === void 0 && value === void 0 && i === path.length - 1) {
        return obj;
      } else if (i < path.length - 1 && (child === void 0 || child === null)) {
        child = initializePathType(pathTypes[i]);
        if (isMap(o)) {
          o.set(p, child);
        } else {
          o[p] = child;
        }
      }
      if (i < path.length - 1) {
        o = child;
        if (oFull) {
          oFull = fullChild;
        }
      }
    }
  }
  if (p === void 0) {
    if (mode === "merge") {
      obj = deepMerge(obj, value);
    } else {
      obj = value;
    }
  } else {
    if (mode === "merge") {
      o[p] = deepMerge(o[p], value);
    } else if (isMap(o)) {
      o.set(p, value);
    } else {
      o[p] = value;
    }
  }
  return obj;
}
function mergeIntoObservable(target, ...sources) {
  if (process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test") {
    if (!isObservable(target)) {
      console.error("[legend-state] should only use mergeIntoObservable with observables");
    }
  }
  beginBatch();
  for (let i = 0; i < sources.length; i++) {
    _mergeIntoObservable(target, sources[i], 0);
  }
  endBatch();
  return target;
}
function _mergeIntoObservable(target, source, levelsDeep) {
  if (isObservable(source)) {
    source = source.peek();
  }
  const targetValue = target.peek();
  const isTargetArr = isArray(targetValue);
  const isTargetObj = !isTargetArr && isObject(targetValue);
  const isSourceMap = isMap(source);
  const isSourceSet = isSet(source);
  if (isSourceSet && isSet(targetValue)) {
    target.set(/* @__PURE__ */ new Set([...source, ...targetValue]));
  } else if (isTargetObj && isObject(source) || isTargetArr && targetValue.length > 0) {
    const keys = isSourceMap || isSourceSet ? Array.from(source.keys()) : Object.keys(source);
    for (let i = 0; i < keys.length; i++) {
      const key = keys[i];
      const sourceValue = isSourceSet ? key : isSourceMap ? source.get(key) : source[key];
      if (sourceValue === symbolDelete) {
        target[key].delete();
      } else {
        const isObj = isObject(sourceValue);
        const isArr = !isObj && isArray(sourceValue);
        const targetChild = target[key];
        if ((isObj || isArr) && targetChild) {
          if (isArr) {
            const sourceArr = sourceValue;
            const isSparseArray = Object.keys(sourceArr).length < sourceArr.length;
            if (isSparseArray) {
              _mergeIntoObservable(targetChild, sourceValue, levelsDeep + 1);
            } else {
              targetChild.set(sourceValue);
            }
          } else if (levelsDeep > 0 && isEmpty(sourceValue)) {
            targetChild.set(sourceValue);
          } else {
            _mergeIntoObservable(targetChild, sourceValue, levelsDeep + 1);
          }
        } else {
          targetChild.set(sourceValue);
        }
      }
    }
  } else if (source !== void 0) {
    target.set(source);
  }
  return target;
}
function constructObjectWithPath(path, pathTypes, value) {
  let out;
  if (path.length > 0) {
    let o = out = {};
    for (let i = 0; i < path.length; i++) {
      const p = path[i];
      o[p] = i === path.length - 1 ? value : initializePathType(pathTypes[i]);
      o = o[p];
    }
  } else {
    out = value;
  }
  return out;
}
function deconstructObjectWithPath(path, pathTypes, value) {
  let o = value;
  for (let i = 0; i < path.length; i++) {
    const p = path[i];
    o = o ? o[p] : initializePathType(pathTypes[i]);
  }
  return o;
}
function isObservableValueReady(value) {
  return !!value && (!isObject(value) && !isArray(value) || !isEmpty(value));
}
function setSilently(value$, newValue) {
  const node = getNode(value$);
  return setNodeValue(node, newValue).newValue;
}
function initializePathType(pathType) {
  switch (pathType) {
    case "array":
      return [];
    case "map":
      return /* @__PURE__ */ new Map();
    case "set":
      return /* @__PURE__ */ new Set();
    case "object":
    default:
      return {};
  }
}
function applyChange(value, change, applyPrevious) {
  const { path, valueAtPath, prevAtPath, pathTypes } = change;
  return setAtPath(value, path, pathTypes, applyPrevious ? prevAtPath : valueAtPath);
}
function applyChanges(value, changes, applyPrevious) {
  for (let i = 0; i < changes.length; i++) {
    value = applyChange(value, changes[i], applyPrevious);
  }
  return value;
}
function deepMerge(target, ...sources) {
  if (isPrimitive(target)) {
    return sources[sources.length - 1];
  }
  let result = isArray(target) ? [...target] : { ...target };
  for (let i = 0; i < sources.length; i++) {
    const obj2 = sources[i];
    if (isPlainObject(obj2) || isArray(obj2)) {
      const objTarget = obj2;
      for (const key in objTarget) {
        if (hasOwnProperty.call(objTarget, key)) {
          if (objTarget[key] instanceof Object && !isObservable(objTarget[key]) && Object.keys(objTarget[key]).length > 0) {
            result[key] = deepMerge(
              result[key] || (isArray(objTarget[key]) ? [] : {}),
              objTarget[key]
            );
          } else {
            result[key] = objTarget[key];
          }
        }
      }
    } else {
      result = obj2;
    }
  }
  return result;
}

// src/batching.ts
var timeout;
var numInBatch = 0;
var isRunningBatch = false;
var didDelayEndBatch = false;
var _batchMap = /* @__PURE__ */ new Map();
function onActionTimeout() {
  if (_batchMap.size > 0) {
    if (process.env.NODE_ENV === "development") {
      console.error(
        "Forcibly completing observableBatcher because end() was never called. This may be due to an uncaught error between begin() and end()."
      );
    }
    endBatch(
      /*force*/
      true
    );
  }
}
function isArraySubset(mainArr, subsetArr) {
  for (let i = 0; i < mainArr.length; i++) {
    if (mainArr[i] !== subsetArr[i]) {
      return false;
    }
  }
  return true;
}
function createPreviousHandlerInner(value, changes) {
  try {
    return applyChanges(value ? clone(value) : {}, changes, true);
  } catch (e) {
    return void 0;
  }
}
function createPreviousHandler(value, changes) {
  return function() {
    return createPreviousHandlerInner(value, changes);
  };
}
function notify(node, value, prev, level, whenOptimizedOnlyIf) {
  const changesInBatch = /* @__PURE__ */ new Map();
  computeChangesRecursive(
    changesInBatch,
    node,
    /*loading*/
    !!globalState.isLoadingLocal,
    /*remote*/
    !!globalState.isLoadingRemote,
    value,
    [],
    [],
    value,
    prev,
    /*immediate*/
    true,
    level,
    whenOptimizedOnlyIf
  );
  const existing = _batchMap.get(node);
  if (existing) {
    if (existing.prev === value) {
      _batchMap.delete(node);
    } else {
      existing.value = value;
    }
  } else {
    _batchMap.set(node, {
      value,
      prev,
      level,
      whenOptimizedOnlyIf,
      isFromSync: !!globalState.isLoadingRemote,
      isFromPersist: !!globalState.isLoadingLocal
    });
  }
  if (changesInBatch.size) {
    batchNotifyChanges(
      changesInBatch,
      /*immediate*/
      true
    );
  }
  if (numInBatch <= 0) {
    runBatch();
  }
}
function computeChangesAtNode(changesInBatch, node, isFromPersist, isFromSync, value, path, pathTypes, valueAtPath, prevAtPath, immediate, level, whenOptimizedOnlyIf) {
  if (immediate ? node.listenersImmediate : node.listeners) {
    const change = {
      path,
      pathTypes,
      valueAtPath,
      prevAtPath
    };
    const changeInBatch = changesInBatch.get(node);
    if (changeInBatch && path.length > 0) {
      const { changes } = changeInBatch;
      if (!isArraySubset(changes[0].path, change.path)) {
        changes.push(change);
        changeInBatch.level = Math.min(changeInBatch.level, level);
        changeInBatch.whenOptimizedOnlyIf || (changeInBatch.whenOptimizedOnlyIf = whenOptimizedOnlyIf);
      }
    } else {
      changesInBatch.set(node, {
        level,
        value,
        isFromSync,
        isFromPersist,
        whenOptimizedOnlyIf,
        changes: [change]
      });
    }
  }
}
function computeChangesRecursive(changesInBatch, node, loading, remote, value, path, pathTypes, valueAtPath, prevAtPath, immediate, level, whenOptimizedOnlyIf) {
  if (node.numListenersRecursive > 0) {
    computeChangesAtNode(
      changesInBatch,
      node,
      loading,
      remote,
      value,
      path,
      pathTypes,
      valueAtPath,
      prevAtPath,
      immediate,
      level,
      whenOptimizedOnlyIf
    );
    if (node.linkedFromNodes) {
      for (const linkedFromNode of node.linkedFromNodes) {
        const childNode = getNodeAtPath(linkedFromNode, path);
        computeChangesRecursive(
          changesInBatch,
          childNode,
          loading,
          remote,
          valueAtPath,
          [],
          [],
          valueAtPath,
          prevAtPath,
          immediate,
          0,
          whenOptimizedOnlyIf
        );
      }
    }
  }
  if (node.parent) {
    const parent = node.parent;
    if (parent) {
      const parentValue = getNodeValue(parent);
      computeChangesRecursive(
        changesInBatch,
        parent,
        loading,
        remote,
        parentValue,
        [node.key].concat(path),
        [getPathType(value)].concat(pathTypes),
        valueAtPath,
        prevAtPath,
        immediate,
        level + 1,
        whenOptimizedOnlyIf
      );
    }
  }
}
function batchNotifyChanges(changesInBatch, immediate) {
  const listenersNotified = /* @__PURE__ */ new Set();
  changesInBatch.forEach(({ changes, level, value, isFromPersist, isFromSync, whenOptimizedOnlyIf }, node) => {
    const listeners = immediate ? node.listenersImmediate : node.listeners;
    if (listeners) {
      let listenerParams;
      const arr = Array.from(listeners);
      for (let i = 0; i < arr.length; i++) {
        const listenerFn = arr[i];
        const { track, noArgs, listener } = listenerFn;
        if (!listenersNotified.has(listener)) {
          const ok = track === true ? level <= 0 : track === optimized ? whenOptimizedOnlyIf && level <= 0 : true;
          if (ok) {
            if (!noArgs && !listenerParams) {
              listenerParams = {
                value,
                isFromPersist,
                isFromSync,
                getPrevious: createPreviousHandler(value, changes),
                changes
              };
            }
            if (!track) {
              listenersNotified.add(listener);
            }
            listener(listenerParams);
          }
        }
      }
    }
  });
}
function runBatch() {
  const dirtyNodes = Array.from(globalState.dirtyNodes);
  globalState.dirtyNodes.clear();
  dirtyNodes.forEach((node) => {
    const dirtyFn = node.dirtyFn;
    if (dirtyFn) {
      node.dirtyFn = void 0;
      dirtyFn();
    }
  });
  const map = _batchMap;
  _batchMap = /* @__PURE__ */ new Map();
  const changesInBatch = /* @__PURE__ */ new Map();
  map.forEach(({ value, prev, level, isFromPersist, isFromSync, whenOptimizedOnlyIf }, node) => {
    computeChangesRecursive(
      changesInBatch,
      node,
      isFromPersist,
      isFromSync,
      value,
      [],
      [],
      value,
      prev,
      false,
      level,
      whenOptimizedOnlyIf
    );
  });
  if (changesInBatch.size) {
    batchNotifyChanges(changesInBatch, false);
  }
}
function batch(fn) {
  beginBatch();
  try {
    fn();
  } finally {
    endBatch();
  }
}
function beginBatch() {
  numInBatch++;
  if (!timeout) {
    timeout = setTimeout(onActionTimeout, 0);
  }
}
function endBatch(force) {
  numInBatch--;
  if (numInBatch <= 0 || force) {
    if (isRunningBatch) {
      didDelayEndBatch = true;
    } else {
      if (timeout) {
        clearTimeout(timeout);
        timeout = void 0;
      }
      numInBatch = 0;
      isRunningBatch = true;
      runBatch();
      isRunningBatch = false;
      if (didDelayEndBatch) {
        didDelayEndBatch = false;
        endBatch(true);
      }
    }
  }
}
function getNodeAtPath(obj, path) {
  let o = obj;
  for (let i = 0; i < path.length; i++) {
    const p = path[i];
    o = getChildNode(o, p);
  }
  return o;
}

// src/createObservable.ts
function createObservable(value, makePrimitive, extractPromise2, createObject, createPrimitive) {
  if (isObservable(value)) {
    return value;
  }
  const valueIsPromise = isPromise(value);
  const valueIsFunction = isFunction(value);
  const root = {
    _: value
  };
  let node = {
    root,
    lazy: true,
    numListenersRecursive: 0
  };
  if (valueIsFunction) {
    node = Object.assign(() => {
    }, node);
    node.lazyFn = value;
  }
  const prim = makePrimitive || isActualPrimitive(value);
  const obs = prim ? new createPrimitive(node) : createObject(node);
  if (valueIsPromise) {
    setNodeValue(node, void 0);
    extractPromise2(node, value);
  }
  return obs;
}

// src/linked.ts
function linked(params, options) {
  if (isFunction(params)) {
    params = { get: params };
  }
  if (options) {
    params = { ...params, ...options };
  }
  const ret = function() {
    return { [symbolLinked]: params };
  };
  ret.prototype[symbolLinked] = params;
  return ret;
}

// src/middleware.ts
var nodeMiddlewareHandlers = /* @__PURE__ */ new WeakMap();
var queuedNodes = [];
var queuedListeners = [];
var queuedTypes = [];
var queueSize = 0;
var isMicrotaskScheduled = false;
function registerMiddleware(node, type, handler) {
  let handlersMap = nodeMiddlewareHandlers.get(node);
  if (!handlersMap) {
    handlersMap = /* @__PURE__ */ new Map();
    nodeMiddlewareHandlers.set(node, handlersMap);
  }
  let handlers = handlersMap.get(type);
  if (!handlers) {
    handlers = /* @__PURE__ */ new Set();
    handlersMap.set(type, handlers);
  }
  handlers.add(handler);
  return () => {
    const handlersMap2 = nodeMiddlewareHandlers.get(node);
    if (!handlersMap2)
      return;
    const handlers2 = handlersMap2.get(type);
    if (!handlers2)
      return;
    handlers2.delete(handler);
    if (handlers2.size === 0) {
      handlersMap2.delete(type);
      if (handlersMap2.size === 0) {
        nodeMiddlewareHandlers.delete(node);
      }
    }
  };
}
function dispatchMiddlewareEvent(node, listener, type) {
  const handlersMap = nodeMiddlewareHandlers.get(node);
  if (!handlersMap || !handlersMap.has(type)) {
    return;
  }
  const handlers = handlersMap.get(type);
  if (!handlers || handlers.size === 0) {
    return;
  }
  queuedNodes[queueSize] = node;
  queuedListeners[queueSize] = listener;
  queuedTypes[queueSize] = type;
  queueSize++;
  if (!isMicrotaskScheduled) {
    isMicrotaskScheduled = true;
    queueMicrotask(processQueuedEvents);
  }
}
var eventObj = {
  type: "listener-added",
  node: null,
  listener: void 0,
  timestamp: 0
};
function processQueuedEvents() {
  isMicrotaskScheduled = false;
  const timestamp = typeof performance !== "undefined" ? performance.now() : Date.now();
  eventObj.timestamp = timestamp;
  for (let i = 0; i < queueSize; i++) {
    const node = queuedNodes[i];
    const listener = queuedListeners[i];
    const type = queuedTypes[i];
    const handlersMap = nodeMiddlewareHandlers.get(node);
    if (!handlersMap)
      continue;
    const handlers = handlersMap.get(type);
    if (!handlers || handlers.size === 0)
      continue;
    const nodeListeners = node.listeners;
    const nodeListenersImmediate = node.listenersImmediate;
    if (!nodeListeners && !nodeListenersImmediate && node.numListenersRecursive && !(type === "listener-added" && !listener)) {
      continue;
    }
    let isValid = false;
    if (type === "listener-added") {
      if (listener) {
        isValid = !!(nodeListeners == null ? void 0 : nodeListeners.has(listener)) || !!(nodeListenersImmediate == null ? void 0 : nodeListenersImmediate.has(listener));
      } else {
        const hasNoLocalListeners = !(nodeListeners == null ? void 0 : nodeListeners.size) && !(nodeListenersImmediate == null ? void 0 : nodeListenersImmediate.size);
        if (hasNoLocalListeners && typeof node.numListenersRecursive === "number") {
          isValid = node.numListenersRecursive > 0;
        } else {
          isValid = false;
        }
      }
    } else if (type === "listener-removed") {
      isValid = !(nodeListeners == null ? void 0 : nodeListeners.has(listener)) && !(nodeListenersImmediate == null ? void 0 : nodeListenersImmediate.has(listener));
    } else {
      const hasAnyLocal = nodeListeners && nodeListeners.size > 0 || nodeListenersImmediate && nodeListenersImmediate.size > 0;
      if (typeof node.numListenersRecursive === "number") {
        isValid = !hasAnyLocal && node.numListenersRecursive === 0;
      } else {
        isValid = !hasAnyLocal;
      }
    }
    if (isValid) {
      eventObj.type = type;
      eventObj.node = node;
      eventObj.listener = listener;
      const iterableHandlers = Array.from(handlers);
      for (let j = 0; j < iterableHandlers.length; j++) {
        try {
          iterableHandlers[j](eventObj);
        } catch (error) {
          console.error(`Error in middleware handler for ${type}:`, error);
        }
      }
    }
  }
  queueSize = 0;
}

// src/onChange.ts
function isSyncedObservable(node) {
  var _a;
  return ((_a = node.activationState) == null ? void 0 : _a.synced) || false;
}
function shouldDispatchParentMiddlewareEvent(node) {
  var _a, _b;
  return !((_a = node.listeners) == null ? void 0 : _a.size) && !((_b = node.listenersImmediate) == null ? void 0 : _b.size) && isSyncedObservable(node);
}
function onChange(node, callback, options = {}, fromLinks) {
  var _a;
  const { initial, immediate, noArgs } = options;
  const { trackingType } = options;
  let listeners = immediate ? node.listenersImmediate : node.listeners;
  if (!listeners) {
    listeners = /* @__PURE__ */ new Set();
    if (immediate) {
      node.listenersImmediate = listeners;
    } else {
      node.listeners = listeners;
    }
  }
  const listener = {
    listener: callback,
    track: trackingType,
    noArgs
  };
  listeners.add(listener);
  if (initial) {
    const value = getNodeValue(node);
    callback({
      value,
      isFromPersist: true,
      isFromSync: false,
      changes: [
        {
          path: [],
          pathTypes: [],
          prevAtPath: value,
          valueAtPath: value
        }
      ],
      getPrevious: () => void 0
    });
  }
  let extraDisposes;
  function addLinkedNodeListeners(childNode, cb = callback, from) {
    if (!(fromLinks == null ? void 0 : fromLinks.has(childNode))) {
      fromLinks || (fromLinks = /* @__PURE__ */ new Set());
      fromLinks.add(from || node);
      cb || (cb = callback);
      const childOptions = {
        trackingType: true,
        ...options
      };
      extraDisposes = [...extraDisposes || [], onChange(childNode, cb, childOptions, fromLinks)];
    }
  }
  if (node.linkedToNode) {
    addLinkedNodeListeners(node.linkedToNode);
  }
  (_a = node.linkedFromNodes) == null ? void 0 : _a.forEach((linkedFromNode) => addLinkedNodeListeners(linkedFromNode));
  node.numListenersRecursive++;
  let parent = node.parent;
  let pathParent = [node.key];
  while (parent) {
    if (parent.linkedFromNodes) {
      for (const linkedFromNode of parent.linkedFromNodes) {
        if (!(fromLinks == null ? void 0 : fromLinks.has(linkedFromNode))) {
          const cb = createCb(linkedFromNode, pathParent, callback);
          addLinkedNodeListeners(linkedFromNode, cb, parent);
        }
      }
    }
    parent.numListenersRecursive++;
    if (shouldDispatchParentMiddlewareEvent(parent)) {
      dispatchMiddlewareEvent(parent, void 0, "listener-added");
    }
    pathParent = [parent.key, ...pathParent];
    parent = parent.parent;
  }
  dispatchMiddlewareEvent(node, listener, "listener-added");
  return () => {
    listeners.delete(listener);
    extraDisposes == null ? void 0 : extraDisposes.forEach((fn) => fn());
    const clearedRecursive = [];
    let parent2 = node;
    while (parent2) {
      parent2.numListenersRecursive--;
      if (parent2.numListenersRecursive === 0) {
        clearedRecursive.push(parent2);
      }
      parent2 = parent2.parent;
    }
    dispatchMiddlewareEvent(node, listener, "listener-removed");
    if (listeners.size === 0) {
      dispatchMiddlewareEvent(node, void 0, "listeners-cleared");
    }
    for (const clearedNode of clearedRecursive) {
      if (clearedNode !== node && shouldDispatchParentMiddlewareEvent(clearedNode)) {
        dispatchMiddlewareEvent(clearedNode, void 0, "listeners-cleared");
      }
    }
  };
}
function createCb(linkedFromNode, path, callback) {
  let prevAtPath = deconstructObjectWithPath(path, [], getNodeValue(linkedFromNode));
  return function({ value: valueA, isFromPersist, isFromSync }) {
    const valueAtPath = deconstructObjectWithPath(path, [], valueA);
    if (valueAtPath !== prevAtPath) {
      callback({
        value: valueAtPath,
        isFromPersist,
        isFromSync,
        changes: [
          {
            path: [],
            pathTypes: [],
            prevAtPath,
            valueAtPath
          }
        ],
        getPrevious: () => prevAtPath
      });
    }
    prevAtPath = valueAtPath;
  };
}

// src/setupTracking.ts
function setupTracking(nodes, update, noArgs, immediate) {
  let listeners = [];
  nodes == null ? void 0 : nodes.forEach((tracked) => {
    const { node, track } = tracked;
    listeners.push(onChange(node, update, { trackingType: track, immediate, noArgs }));
  });
  return () => {
    if (listeners) {
      for (let i = 0; i < listeners.length; i++) {
        listeners[i]();
      }
      listeners = void 0;
    }
  };
}

// src/tracking.ts
var trackCount = 0;
var trackingQueue = [];
var tracking = {
  current: void 0
};
function beginTracking() {
  trackingQueue.push(tracking.current);
  trackCount++;
  tracking.current = {};
}
function endTracking() {
  trackCount--;
  if (trackCount < 0) {
    trackCount = 0;
  }
  tracking.current = trackingQueue.pop();
}
function updateTracking(node, track) {
  if (trackCount) {
    const tracker = tracking.current;
    if (tracker) {
      if (!tracker.nodes) {
        tracker.nodes = /* @__PURE__ */ new Map();
      }
      const existing = tracker.nodes.get(node);
      if (existing) {
        existing.track = existing.track || track;
        existing.num++;
      } else {
        tracker.nodes.set(node, { node, track, num: 1 });
      }
    }
  }
}

// src/trackSelector.ts
function trackSelector(selector, update, getOptions, observeEvent, observeOptions, createResubscribe) {
  var _a;
  let dispose;
  let resubscribe;
  let updateFn = update;
  beginTracking();
  const value = selector ? computeSelector(selector, getOptions, observeEvent, observeOptions == null ? void 0 : observeOptions.fromComputed) : selector;
  const tracker = tracking.current;
  const nodes = tracker.nodes;
  endTracking();
  if ((process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test") && tracker && nodes) {
    (_a = tracker.traceListeners) == null ? void 0 : _a.call(tracker, nodes);
    if (tracker.traceUpdates) {
      updateFn = tracker.traceUpdates(update);
    }
    tracker.traceListeners = void 0;
    tracker.traceUpdates = void 0;
  }
  if (!(observeEvent == null ? void 0 : observeEvent.cancel)) {
    dispose = setupTracking(nodes, updateFn, false, observeOptions == null ? void 0 : observeOptions.immediate);
    if (process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test") {
      resubscribe = createResubscribe ? () => {
        dispose == null ? void 0 : dispose();
        dispose = setupTracking(nodes, updateFn);
        return dispose;
      } : void 0;
    }
  }
  return { nodes, value, dispose, resubscribe };
}

// src/observe.ts
function observe(selectorOrRun, reactionOrOptions, options) {
  let reaction;
  if (isFunction(reactionOrOptions)) {
    reaction = reactionOrOptions;
  } else {
    options = reactionOrOptions;
  }
  let dispose;
  let isRunning = false;
  const e = { num: 0 };
  const update = function() {
    if (isRunning) {
      return;
    }
    if (e.onCleanup) {
      e.onCleanup();
      e.onCleanup = void 0;
    }
    isRunning = true;
    beginBatch();
    delete e.value;
    dispose == null ? void 0 : dispose();
    const {
      dispose: _dispose,
      value,
      nodes
    } = trackSelector(selectorOrRun, update, void 0, e, options);
    dispose = _dispose;
    e.value = value;
    e.nodes = nodes;
    e.refresh = update;
    if (e.onCleanupReaction) {
      e.onCleanupReaction();
      e.onCleanupReaction = void 0;
    }
    endBatch();
    isRunning = false;
    if (reaction && ((options == null ? void 0 : options.fromComputed) || (e.num > 0 || !isEvent(selectorOrRun)) && (e.previous !== e.value || typeof e.value === "object"))) {
      reaction(e);
    }
    e.previous = e.value;
    e.num++;
  };
  update();
  return () => {
    var _a, _b;
    (_a = e.onCleanup) == null ? void 0 : _a.call(e);
    e.onCleanup = void 0;
    (_b = e.onCleanupReaction) == null ? void 0 : _b.call(e);
    e.onCleanupReaction = void 0;
    dispose == null ? void 0 : dispose();
  };
}

// src/toPrimitive.ts
function toPrimitive(node, hint) {
  const value = peek(node);
  if (value === null || value === void 0 || isPrimitive(value)) {
    return value;
  }
  const method = hint === "string" ? isFunction(value.toString) ? value.toString : value.valueOf : isFunction(value.valueOf) ? value.valueOf : value.toString;
  return isFunction(method) ? method.call(value) : value;
}

// src/when.ts
function _when(predicate, effect, checkReady) {
  if (isPromise(predicate)) {
    return effect ? predicate.then(effect) : predicate;
  }
  const isPredicateArray = isArray(predicate);
  let value;
  let effectValue;
  function run(e) {
    const ret = isPredicateArray ? predicate.map((p) => computeSelector(p)) : computeSelector(predicate);
    if (isPromise(ret)) {
      value = ret;
      return void 0;
    } else {
      let isOk = true;
      if (isArray(ret)) {
        for (let i = 0; i < ret.length; i++) {
          let item = ret[i];
          if (isObservable(item)) {
            item = computeSelector(item);
          } else if (isFunction(item)) {
            item = item();
          }
          isOk = isOk && !!(checkReady ? isObservableValueReady(item) : item);
        }
      } else {
        isOk = checkReady ? isObservableValueReady(ret) : ret;
      }
      if (isOk) {
        value = ret;
        e.cancel = true;
      }
    }
    return value;
  }
  function doEffect() {
    effectValue = effect == null ? void 0 : effect(value);
  }
  observe(run, doEffect);
  if (isPromise(value)) {
    return effect ? value.then(effect) : value;
  } else if (value !== void 0) {
    return effect ? effectValue : Promise.resolve(value);
  } else {
    const promise = new Promise((resolve) => {
      if (effect) {
        const originalEffect = effect;
        effect = (value2) => {
          const effectValue2 = originalEffect(value2);
          resolve(isPromise(effectValue2) ? effectValue2.then((value3) => value3) : effectValue2);
        };
      } else {
        effect = resolve;
      }
    });
    return promise;
  }
}
function when(predicate, effect) {
  return _when(predicate, effect, false);
}
function whenReady(predicate, effect) {
  return _when(predicate, effect, true);
}

// src/ObservableObject.ts
var ArrayModifiers = /* @__PURE__ */ new Set([
  "copyWithin",
  "fill",
  "from",
  "pop",
  "push",
  "reverse",
  "shift",
  "sort",
  "splice",
  "unshift"
]);
var ArrayLoopers = /* @__PURE__ */ new Set([
  "every",
  "filter",
  "find",
  "findIndex",
  "flatMap",
  "forEach",
  "join",
  "map",
  "reduce",
  "some"
]);
var ArrayLoopersReturn = /* @__PURE__ */ new Set(["filter", "find"]);
var observableProperties = /* @__PURE__ */ new Map();
var observableFns = /* @__PURE__ */ new Map([
  ["get", get],
  ["set", set],
  ["peek", peek],
  ["onChange", onChange],
  ["assign", assign],
  ["delete", deleteFn],
  ["toggle", toggle]
]);
if (process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test") {
  __devUpdateNodes = /* @__PURE__ */ new Set();
}
var __devUpdateNodes;
function collectionSetter(node, target, prop, ...args) {
  var _a;
  if (prop === "push" && args.length === 1) {
    setKey(node, target.length + "", args[0]);
  } else {
    const prevValue = target.slice();
    const ret = target[prop].apply(target, args);
    if (node) {
      const hasParent = isChildNode(node);
      const key = hasParent ? node.key : "_";
      const parentValue = hasParent ? getNodeValue(node.parent) : node.root;
      parentValue[key] = prevValue;
      setKey((_a = node.parent) != null ? _a : node, key, target);
    }
    return ret;
  }
}
function updateNodes(parent, obj, prevValue) {
  var _a, _b, _c;
  if ((process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test") && typeof __devUpdateNodes !== "undefined" && isObject(obj)) {
    if (__devUpdateNodes.has(obj)) {
      console.error(
        "[legend-state] Circular reference detected in object. You may want to use opaqueObject to stop traversing child nodes.",
        obj
      );
      return false;
    }
    __devUpdateNodes.add(obj);
  }
  if (isObject(obj) && isHintOpaque(obj) || isObject(prevValue) && isHintOpaque(prevValue)) {
    const isDiff = obj !== prevValue;
    if (isDiff) {
      if (parent.listeners || parent.listenersImmediate) {
        notify(parent, obj, prevValue, 0);
      }
    }
    if ((process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test") && typeof __devUpdateNodes !== "undefined" && obj !== void 0) {
      __devUpdateNodes.delete(obj);
    }
    return isDiff;
  }
  const isArr = isArray(obj);
  let prevChildrenById;
  let moved;
  const isCurMap = isMap(obj);
  const isCurSet = isSet(obj);
  const isPrevMap = isMap(prevValue);
  const isPrevSet = isSet(prevValue);
  const keys = getKeys(obj, isArr, isCurMap, isCurSet);
  const keysPrev = getKeys(prevValue, isArr, isPrevMap, isPrevSet);
  const length = ((_a = keys || obj) == null ? void 0 : _a.length) || 0;
  const lengthPrev = ((_b = keysPrev || prevValue) == null ? void 0 : _b.length) || 0;
  let idField;
  let isIdFieldFunction;
  let hasADiff = false;
  let retValue;
  if (isArr && isArray(prevValue)) {
    if (prevValue.length > 0) {
      const firstPrevValue = prevValue[0];
      if (firstPrevValue !== void 0) {
        idField = findIDKey(firstPrevValue, parent);
        if (idField) {
          isIdFieldFunction = isFunction(idField);
          prevChildrenById = /* @__PURE__ */ new Map();
          moved = [];
        }
        const keysSeen = process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test" ? /* @__PURE__ */ new Set() : void 0;
        if (parent.children) {
          for (let i = 0; i < prevValue.length; i++) {
            const p = prevValue[i];
            if (p) {
              const child = parent.children.get(i + "");
              if (child) {
                if (!obj[i]) {
                  handleDeletedChild(child, p);
                }
                if (idField) {
                  const key = isIdFieldFunction ? idField(p) : p[idField];
                  if (process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test") {
                    if (keysSeen.has(key)) {
                      console.warn(
                        `[legend-state] Warning: Multiple elements in array have the same ID. Key field: ${idField}, Array:`,
                        prevValue
                      );
                    }
                    keysSeen.add(key);
                  }
                  prevChildrenById.set(key, child);
                }
              }
            }
          }
        }
      }
    }
  } else if (prevValue && (!obj || isObject(obj))) {
    const lengthPrev2 = keysPrev.length;
    for (let i = 0; i < lengthPrev2; i++) {
      const key = keysPrev[i];
      if (!keys.includes(key)) {
        hasADiff = true;
        const child = getChildNode(parent, key);
        const prev = isPrevMap ? prevValue.get(key) : prevValue[key];
        if (prev !== void 0) {
          handleDeletedChild(child, prev);
        }
      }
    }
  }
  if (obj && !isPrimitive(obj)) {
    hasADiff = hasADiff || length !== lengthPrev;
    const isArrDiff = hasADiff;
    let didMove = false;
    for (let i = 0; i < length; i++) {
      const key = isArr ? i + "" : keys[i];
      let value = isCurMap ? obj.get(key) : obj[key];
      const prev = isPrevMap ? prevValue == null ? void 0 : prevValue.get(key) : prevValue == null ? void 0 : prevValue[key];
      let isDiff = !equals(value, prev);
      if (isDiff) {
        const id = idField && value ? isIdFieldFunction ? idField(value) : value[idField] : void 0;
        const existingChild = (_c = parent.children) == null ? void 0 : _c.get(key);
        if (isObservable(value)) {
          const valueNode = getNode(value);
          if ((existingChild == null ? void 0 : existingChild.linkedToNode) === valueNode) {
            const targetValue = getNodeValue(valueNode);
            isCurMap ? obj.set(key, targetValue) : obj[key] = targetValue;
            continue;
          }
          const obs = value;
          value = () => obs;
        }
        let child = getChildNode(parent, key, value);
        if (!child.lazy && (isFunction(value) || isObservable(value))) {
          reactivateNode(child, value);
          peekInternal(child);
        }
        if (isArr && id !== void 0) {
          const prevChild = id !== void 0 ? prevChildrenById == null ? void 0 : prevChildrenById.get(id) : void 0;
          if (!prevChild) {
            hasADiff = true;
          } else if (prevChild !== void 0 && prevChild.key !== key) {
            const valuePrevChild = prevValue[prevChild.key];
            if (isArrDiff) {
              child = prevChild;
              parent.children.delete(child.key);
              child.key = key;
              moved.push([key, child]);
            }
            didMove = true;
            isDiff = valuePrevChild !== value;
          }
        }
        if (isDiff) {
          if (isFunction(value) || isObservable(value)) {
            extractFunctionOrComputed(parent, key, value);
          } else if (isPrimitive(value)) {
            hasADiff = true;
          } else {
            const updatedNodes = updateNodes(child, value, prev);
            hasADiff = hasADiff || updatedNodes;
            isDiff = updatedNodes;
          }
        }
        if (isDiff || isArr && !isArrDiff) {
          if (child.listeners || child.listenersImmediate) {
            notify(child, value, prev, 0, !isArrDiff);
          }
        }
      }
    }
    if (moved) {
      for (let i = 0; i < moved.length; i++) {
        const [key, child] = moved[i];
        parent.children.set(key, child);
      }
    }
    if (isArr && length < lengthPrev && parent.children) {
      for (let i = length; i < lengthPrev; i++) {
        const key = i + "";
        const child = parent.children.get(key);
        if (child) {
          handleDeletedChild(child, prevValue == null ? void 0 : prevValue[i]);
          parent.children.delete(key);
        }
      }
    }
    retValue = hasADiff || didMove;
  } else if (prevValue !== void 0) {
    retValue = true;
  }
  if ((process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test") && typeof __devUpdateNodes !== "undefined" && obj !== void 0) {
    __devUpdateNodes.delete(obj);
  }
  return retValue != null ? retValue : false;
}
function handleDeletedChild(child, p) {
  var _a, _b;
  deactivateNode(child);
  (_b = (_a = child.parent) == null ? void 0 : _a.functions) == null ? void 0 : _b.delete(child.key);
  if (!isPrimitive(p)) {
    updateNodes(child, void 0, p);
  }
  if (child.listeners || child.listenersImmediate) {
    notify(child, void 0, p, 0);
  }
}
function getProxy(node, p, asFunction) {
  if (p !== void 0)
    node = getChildNode(node, p, asFunction);
  return node.proxy || (node.proxy = new Proxy(node, proxyHandler));
}
function flushPending() {
  if (globalState.pendingNodes.size > 0) {
    const nodes = Array.from(globalState.pendingNodes.values());
    globalState.pendingNodes.clear();
    nodes.forEach((fn) => fn());
  }
}
var proxyHandler = {
  get(node, p, receiver) {
    var _a, _b, _c;
    if (p === symbolToPrimitive) {
      return (hint) => toPrimitive(node, hint);
    }
    if (p === symbolGetNode) {
      return node;
    }
    if (p === "apply" || p === "call") {
      const nodeValue = getNodeValue(node);
      if (isFunction(nodeValue)) {
        return nodeValue[p];
      }
    }
    if (p === "constructor") {
      const ctor = (_a = peekInternal(node)) == null ? void 0 : _a.constructor;
      return typeof ctor === "function" ? ctor : Object;
    }
    let value = peekInternal(
      node,
      /*activateRecursive*/
      p === "get" || p === "peek"
    );
    if (p === symbolIterator) {
      return !value || isPrimitive(value) ? void 0 : value[p];
    }
    const targetNode = node.linkedToNode || (value == null ? void 0 : value[symbolGetNode]);
    if (targetNode && p !== "onChange") {
      return proxyHandler.get(targetNode, p, receiver);
    }
    if (isMap(value) || isSet(value)) {
      const ret = handlerMapSet(node, p, value);
      if (ret !== void 0) {
        return ret;
      }
    }
    const fn = observableFns.get(p);
    if (fn) {
      if (p === "get" || p === "peek") {
        flushPending();
      }
      return function(a, b, c) {
        const l = arguments.length;
        switch (l) {
          case 0:
            return fn(node);
          case 1:
            return fn(node, a);
          case 2:
            return fn(node, a, b);
          default:
            return fn(node, a, b, c);
        }
      };
    }
    const property = observableProperties.get(p);
    if (property) {
      return property.get(node);
    }
    let vProp = value == null ? void 0 : value[p];
    if (isObject(value) && isHintOpaque(value)) {
      return vProp;
    }
    const fnOrComputed = (_b = node.functions) == null ? void 0 : _b.get(p);
    if (fnOrComputed) {
      if (isObservable(fnOrComputed)) {
        return fnOrComputed;
      } else {
        return getProxy(node, p, fnOrComputed);
      }
    } else {
      vProp = checkProperty(value, p);
    }
    if (isNullOrUndefined(value) && vProp === void 0 && (ArrayModifiers.has(p) || ArrayLoopers.has(p))) {
      value = [];
      if (ArrayModifiers.has(p))
        setNodeValue(node, value);
      vProp = value[p];
    }
    if (isFunction(vProp)) {
      if (isArray(value)) {
        if (ArrayModifiers.has(p)) {
          return (...args) => collectionSetter(node, value, p, ...args);
        } else if (ArrayLoopers.has(p)) {
          updateTracking(node, true);
          return function(cbOrig, thisArg) {
            const isReduce = p === "reduce";
            const cbWrapped = isReduce ? (previousValue, currentValue, currentIndex, array) => {
              return cbOrig(
                previousValue,
                getProxy(node, currentIndex + "", currentValue),
                currentIndex,
                array
              );
            } : (val, index, array) => {
              return cbOrig(getProxy(node, index + "", val), index, array);
            };
            if (isReduce || !ArrayLoopersReturn.has(p)) {
              return value[p](cbWrapped, thisArg);
            }
            const isFind = p === "find";
            const out = [];
            for (let i = 0; i < value.length; i++) {
              if (cbWrapped(value[i], i, value)) {
                const proxy2 = getProxy(node, i + "");
                if (isFind) {
                  return proxy2;
                }
                out.push(proxy2);
              }
            }
            return isFind ? void 0 : out;
          };
        }
      }
      extractFunctionOrComputed(node, p, vProp);
      const fnOrComputed2 = (_c = node.functions) == null ? void 0 : _c.get(p);
      if (fnOrComputed2) {
        return getProxy(node, p, fnOrComputed2);
      }
      return vProp.bind(value);
    }
    if (isPrimitive(vProp)) {
      if (p === "length" && isArray(value)) {
        updateTracking(node, true);
        return vProp;
      }
    }
    return getProxy(node, p);
  },
  // Forward all proxy properties to the target's value
  getPrototypeOf(node) {
    const value = getNodeValue(node);
    return value !== null && typeof value === "object" ? Reflect.getPrototypeOf(value) : null;
  },
  ownKeys(node) {
    peekInternal(node);
    const value = get(node, true);
    if (isPrimitive(value))
      return [];
    const keys = value ? Reflect.ownKeys(value) : [];
    if (isArray(value) && keys[keys.length - 1] === "length") {
      keys.splice(keys.length - 1, 1);
    }
    if (isFunction(node)) {
      const reflectedKeys = Reflect.ownKeys(node);
      ["caller", "arguments", "prototype"].forEach((key) => reflectedKeys.includes(key) && keys.push(key));
    }
    return keys;
  },
  getOwnPropertyDescriptor(node, prop) {
    if (prop === "caller" || prop === "arguments" || prop === "prototype") {
      return { configurable: false, enumerable: false };
    }
    const value = getNodeValue(node);
    if (isPrimitive(value)) {
      return void 0;
    }
    const descriptor = Reflect.getOwnPropertyDescriptor(value, prop);
    return descriptor ? { ...descriptor, configurable: true } : void 0;
  },
  set(node, prop, value) {
    if (node.isSetting) {
      return Reflect.set(node, prop, value);
    }
    if (node.isAssigning) {
      setKey(node, prop, value);
      return true;
    }
    const property = observableProperties.get(prop);
    if (property) {
      property.set(node, value);
      return true;
    }
    if (process.env.NODE_ENV === "development") {
      console.warn("[legend-state]: Error: Cannot set a value directly:", prop, value);
    }
    return false;
  },
  deleteProperty(node, prop) {
    if (node.isSetting) {
      return Reflect.deleteProperty(node, prop);
    } else {
      if (process.env.NODE_ENV === "development") {
        console.warn("[legend-state]: Error: Cannot delete a value directly:", prop);
      }
      return false;
    }
  },
  has(node, prop) {
    const value = getNodeValue(node);
    if (value === void 0 || value === null) {
      return false;
    }
    if (typeof value === "object" || typeof value === "function") {
      return Reflect.has(value, prop);
    }
    return false;
  },
  apply(target, thisArg, argArray) {
    if (isObservable(thisArg)) {
      thisArg = thisArg.peek();
    }
    const fnRaw = getNodeValue(target);
    const fn = isFunction(fnRaw) ? fnRaw : target.lazyFn || target;
    return Reflect.apply(fn, thisArg, argArray);
  }
};
function set(node, newValue) {
  if (node.parent) {
    setKey(node.parent, node.key, newValue);
  } else {
    setKey(node, "_", newValue);
  }
}
function toggle(node) {
  const value = getNodeValue(node);
  if (value === void 0 || value === null || isBoolean(value)) {
    set(node, !value);
  } else if (process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test") {
    throw new Error("[legend-state] Cannot toggle a non-boolean value");
  }
}
function setKey(node, key, newValue, level) {
  if (process.env.NODE_ENV === "development") {
    if (typeof HTMLElement !== "undefined" && newValue instanceof HTMLElement) {
      console.warn(`[legend-state] Set an HTMLElement into state. You probably don't want to do that.`);
    }
  }
  const isRoot = !node.parent && key === "_";
  if (node.parent && !getNodeValue(node) && !isFunction(newValue)) {
    set(node, { [key]: newValue });
  }
  const childNode = isRoot ? node : getChildNode(node, key, newValue);
  checkPlain(childNode, newValue);
  if (isObservable(newValue)) {
    setToObservable(childNode, newValue);
  } else {
    const {
      newValue: savedValue,
      prevValue,
      parentValue,
      parentHadKey,
      parentHasKey
    } = setNodeValue(childNode, newValue);
    const isPrim = isPrimitive(prevValue) || prevValue instanceof Date || isTemporal(prevValue) || isPrimitive(savedValue) || savedValue instanceof Date || isTemporal(savedValue);
    if (!isPrim) {
      let parent = childNode;
      do {
        parent.needsExtract = true;
        parent.recursivelyAutoActivated = false;
      } while (parent = parent.parent);
    }
    const notify2 = !equals(savedValue, prevValue);
    const forceNotify = !notify2 && childNode.isComputing && !isPrim && !childNode.isPlain;
    if ((notify2 || forceNotify) && !(childNode.isComputing && childNode.isPlain && node.numListenersRecursive === 0)) {
      updateNodesAndNotify(
        node,
        savedValue,
        prevValue,
        childNode,
        parentValue,
        isPrim,
        isRoot,
        level,
        forceNotify,
        parentHadKey !== parentHasKey
      );
    }
    extractFunctionOrComputed(node, key, savedValue);
  }
}
function assign(node, value) {
  const proxy2 = getProxy(node);
  beginBatch();
  if (isPrimitive(node.root._)) {
    node.root._ = {};
  }
  if (isMap(value)) {
    const currentValue = getNodeValue(node);
    if (isMap(currentValue)) {
      value.forEach((value2, key) => currentValue.set(key, value2));
    } else {
      set(node, value);
    }
  } else {
    node.isAssigning = (node.isAssigning || 0) + 1;
    try {
      Object.assign(proxy2, value);
    } finally {
      node.isAssigning--;
    }
  }
  endBatch();
  return proxy2;
}
function deleteFn(node, key) {
  if (key === void 0 && isChildNode(node)) {
    key = node.key;
    node = node.parent;
  }
  const value = getNodeValue(node);
  if (isArray(value)) {
    collectionSetter(node, value, "splice", key, 1);
  } else {
    setKey(
      node,
      key != null ? key : "_",
      symbolDelete,
      /*level*/
      -1
    );
  }
}
function handlerMapSet(node, p, value) {
  const vProp = value == null ? void 0 : value[p];
  if (p === "size") {
    updateTracking(node, true);
    return value[p];
  } else if (isFunction(vProp)) {
    return function(a, b, c) {
      const l = arguments.length;
      const valueMapOrSet = value;
      if (p === "get") {
        if (l > 0 && typeof a !== "boolean" && a !== optimized) {
          return getProxy(node, a);
        }
      } else if (p === "set") {
        if (l === 2) {
          set(getChildNode(node, a), b);
        } else if (l === 1 && isMap(value)) {
          set(node, a);
        }
        return getProxy(node);
      } else if (p === "delete") {
        if (l > 0) {
          const prev = value.get ? valueMapOrSet.get(a) : a;
          deleteFn(node, a);
          return prev !== void 0;
        }
      } else if (p === "clear") {
        const prev = isSet(valueMapOrSet) ? new Set(valueMapOrSet) : new Map(valueMapOrSet);
        const size = valueMapOrSet.size;
        valueMapOrSet.clear();
        if (size) {
          updateNodesAndNotify(node, value, prev);
        }
        return;
      } else if (p === "add") {
        const prev = new Set(value);
        const ret = value.add(a);
        if (!value.has(p)) {
          notify(node, ret, prev, 0);
        }
        return getProxy(node);
      }
      const fn = observableFns.get(p);
      if (fn) {
        switch (l) {
          case 0:
            return fn(node);
          case 1:
            return fn(node, a);
          case 2:
            return fn(node, a, b);
          default:
            return fn(node, a, b, c);
        }
      } else {
        return value[p](a, b);
      }
    };
  }
}
function updateNodesAndNotify(node, newValue, prevValue, childNode, parentValue, isPrim, isRoot, level, forceNotify, parentKeyChanged) {
  if (!childNode)
    childNode = node;
  beginBatch();
  if (isPrim === void 0) {
    isPrim = isPrimitive(newValue);
  }
  let hasADiff = forceNotify || isPrim;
  let whenOptimizedOnlyIf = false;
  let valueAsArr;
  let valueAsMap;
  let valueAsObj;
  if (!isPrim || prevValue && !isPrimitive(prevValue)) {
    if ((process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test") && typeof __devUpdateNodes !== "undefined") {
      __devUpdateNodes.clear();
    }
    hasADiff = hasADiff || updateNodes(childNode, newValue, prevValue);
    if (isArray(newValue)) {
      valueAsArr = newValue;
    } else if (isMap(newValue) || isSet(newValue)) {
      valueAsMap = newValue;
    } else if (isObject(newValue)) {
      valueAsObj = newValue;
    }
  }
  if (isArray(parentValue)) {
    valueAsArr = parentValue;
  } else if (isMap(parentValue) || isSet(parentValue)) {
    valueAsMap = parentValue;
  }
  if (valueAsArr) {
    whenOptimizedOnlyIf = (valueAsArr == null ? void 0 : valueAsArr.length) !== (prevValue == null ? void 0 : prevValue.length);
  } else if (valueAsMap) {
    whenOptimizedOnlyIf = (valueAsMap == null ? void 0 : valueAsMap.size) !== (prevValue == null ? void 0 : prevValue.size);
  } else if (valueAsObj) {
    const keys = Object.keys(valueAsObj);
    const prevValueAsObj = isObject(prevValue) ? prevValue : {};
    const prevKeys = Object.keys(prevValueAsObj);
    whenOptimizedOnlyIf = keys.length !== prevKeys.length || keys.some((key) => !hasOwnProperty.call(prevValueAsObj, key));
  } else if (isObject(parentValue)) {
    whenOptimizedOnlyIf = !!parentKeyChanged;
  }
  if (isPrim || !newValue || isEmpty(newValue) && !isEmpty(prevValue) ? newValue !== prevValue : hasADiff) {
    notify(
      isPrim && isRoot ? node : childNode,
      newValue,
      prevValue,
      (level != null ? level : prevValue === void 0) ? -1 : hasADiff ? 0 : 1,
      whenOptimizedOnlyIf
    );
  }
  endBatch();
}
function extractPromise(node, value, setter) {
  const numGets = node.numGets = (node.numGets || 0) + 1;
  if (!node.state) {
    node.state = createObservable(
      {
        isLoaded: false
      },
      false,
      extractPromise,
      getProxy
    );
  }
  value.then((value2) => {
    if (numGets >= (node.getNumResolved || 0)) {
      node.getNumResolved = node.numGets;
      setter ? setter({ value: value2 }) : set(node, value2);
      node.state.assign({
        isLoaded: true,
        error: void 0
      });
    }
  }).catch((error) => {
    node.state.error.set(error);
  });
}
function extractFunctionOrComputed(node, k, v) {
  if (isPromise(v)) {
    const childNode = getChildNode(node, k);
    extractPromise(childNode, v);
    setNodeValue(childNode, void 0);
    return void 0;
  } else if (isObservable(v)) {
    const fn = () => v;
    extractFunction(node, k, fn);
    const childNode = getChildNode(node, k, fn);
    const targetNode = getNode(v);
    const initialValue = peek(targetNode);
    setToObservable(childNode, v);
    setNodeValue(childNode, initialValue);
    return getNodeValue(childNode);
  } else if (typeof v === "function") {
    extractFunction(node, k, v);
    return k;
  }
}
function get(node, options) {
  const track = options ? isObject(options) ? options.shallow : options : void 0;
  updateTracking(node, track);
  return peek(node);
}
function peek(node) {
  return peekInternal(node, true);
}
var isFlushing = false;
function peekInternal(node, activateRecursive) {
  var _a;
  isFlushing = true;
  if (activateRecursive && ((_a = node.dirtyChildren) == null ? void 0 : _a.size)) {
    const dirty = Array.from(node.dirtyChildren);
    node.dirtyChildren.clear();
    dirty.forEach((node2) => node2.dirtyFn && peekInternal(node2));
  }
  if (node.dirtyFn) {
    const dirtyFn = node.dirtyFn;
    node.dirtyFn = void 0;
    globalState.dirtyNodes.delete(node);
    dirtyFn();
  }
  isFlushing = false;
  let value = getNodeValue(node);
  if (!node.root.isLoadingLocal && !node.isPlain) {
    value = checkLazy(node, value, !!activateRecursive);
  }
  return value;
}
function checkLazy(node, value, activateRecursive) {
  const origValue = value;
  const lazy = node.lazy;
  if (lazy) {
    const lazyFn = node.lazyFn;
    delete node.lazy;
    if (isFunction(lazyFn)) {
      if (lazyFn.length === 1) {
        value = {};
      } else {
        if (node.parent) {
          const parentValue = getNodeValue(node.parent);
          if (isFunction(value)) {
            if (parentValue) {
              delete parentValue[node.key];
            } else {
              node.root._ = void 0;
            }
          }
        }
        value = activateNodeFunction(node, lazyFn);
      }
    } else if (isObservable(value)) {
      value = extractFunctionOrComputed(node.parent, node.key, value);
    }
  }
  checkPlain(node, value);
  if ((lazy || node.needsExtract) && !node.isPlain && !isObservable(value) && !isPrimitive(value)) {
    if (activateRecursive) {
      recursivelyAutoActivate(value, node);
    }
    if (node.parent) {
      extractFunctionOrComputed(node.parent, node.key, origValue);
    }
  }
  return value;
}
function checkProperty(value, key) {
  if (value) {
    const property = Object.getOwnPropertyDescriptor(value, key);
    if (property == null ? void 0 : property.get) {
      delete value[key];
      value[key] = property.set ? linked({
        get: property.get,
        set: ({ value: value2 }) => property.set(value2)
      }) : property.get;
    }
    return value[key];
  }
}
function deactivateNode(node) {
  var _a, _b;
  (_a = node.activatedObserveDispose) == null ? void 0 : _a.call(node);
  (_b = node.linkedToNodeDispose) == null ? void 0 : _b.call(node);
  node.activatedObserveDispose = node.linkedToNodeDispose = node.linkedToNode = void 0;
}
function reactivateNode(node, lazyFn) {
  deactivateNode(node);
  node.lazyFn = lazyFn;
  node.lazy = true;
}
function isObserved(node) {
  var _a, _b;
  let parent = node;
  let hasListeners = node.numListenersRecursive > 0;
  while (parent && !hasListeners) {
    if (!!((_a = parent.listeners) == null ? void 0 : _a.size) || !!((_b = parent.listenersImmediate) == null ? void 0 : _b.size)) {
      hasListeners = true;
    }
    parent = parent.parent;
  }
  return hasListeners;
}
function shouldIgnoreUnobserved(node, refreshFn) {
  if (!isFlushing) {
    const hasListeners = isObserved(node);
    if (!hasListeners) {
      if (refreshFn) {
        node.dirtyFn = refreshFn;
      }
      let parent = node;
      while (parent) {
        if (!parent.dirtyChildren) {
          parent.dirtyChildren = /* @__PURE__ */ new Set();
        }
        parent.dirtyChildren.add(node);
        parent = parent.parent;
      }
      return true;
    }
  }
}
function activateNodeFunction(node, lazyFn) {
  let update;
  let wasPromise;
  let ignoreThisUpdate;
  let isFirst = true;
  const activateFn = lazyFn;
  let activatedValue;
  let disposes = [];
  let refreshFn;
  function markDirty() {
    node.dirtyFn = refreshFn;
    globalState.dirtyNodes.add(node);
  }
  const observeDispose = observe(
    () => {
      var _a, _b, _c, _d;
      if (isFirst) {
        isFirst = false;
        if (isFunction(getNodeValue(node))) {
          setNodeValue(node, void 0);
        }
      } else if (!isFlushing && refreshFn) {
        if (shouldIgnoreUnobserved(node, refreshFn)) {
          ignoreThisUpdate = true;
          return;
        }
      }
      let value = activateFn();
      let didSetToObs = false;
      const isObs = isObservable(value);
      if (isObs || node.linkedToNode) {
        didSetToObs = isObs;
        value = setToObservable(node, value);
      }
      if (isFunction(value) && value.length === 0) {
        value = value();
      }
      const activated = !isObs ? value == null ? void 0 : value[symbolLinked] : void 0;
      if (activated) {
        node.activationState = activated;
        value = void 0;
      }
      ignoreThisUpdate = false;
      wasPromise = isPromise(value);
      if (!node.activated) {
        node.activated = true;
        let activateNodeFn = activateNodeBase;
        if (activated == null ? void 0 : activated.synced) {
          activateNodeFn = globalState.activateSyncedNode;
          ignoreThisUpdate = true;
        }
        const result = activateNodeFn(node, value);
        update = result.update;
        let newValue = result.value;
        if (!didSetToObs && isObservable(newValue)) {
          newValue = setToObservable(node, newValue);
        }
        value = newValue != null ? newValue : activated == null ? void 0 : activated.initial;
      } else if (node.activationState) {
        const activated2 = node.activationState;
        if ((_b = (_a = node.state) == null ? void 0 : _a.peek()) == null ? void 0 : _b.sync) {
          node.state.sync();
          ignoreThisUpdate = true;
        } else {
          value = (_d = (_c = activated2.get) == null ? void 0 : _c.call(activated2)) != null ? _d : activated2.initial;
        }
      }
      if (ignoreThisUpdate) {
        activatedValue = value;
      }
      wasPromise = wasPromise || isPromise(value);
      return value;
    },
    (e) => {
      const { value, nodes, refresh } = e;
      refreshFn = refresh;
      if (!ignoreThisUpdate) {
        if (!wasPromise || !globalState.isLoadingRemote) {
          if (wasPromise) {
            if (node.activationState) {
              const { initial } = node.activationState;
              if (value && isPromise(value)) {
                extractPromise(node, value, update);
              }
              if (isFunction(getNodeValue(node))) {
                setNodeValue(node, initial != null ? initial : void 0);
              }
            } else if (node.activated) {
              extractPromise(node, value, update);
              if (isFunction(getNodeValue(node))) {
                setNodeValue(node, void 0);
              }
            }
          } else {
            activatedValue = value;
            const isLoaded = node.state.isLoaded.peek();
            if (isLoaded || !isFunction(value)) {
              node.isComputing = true;
              set(node, value);
              node.isComputing = false;
            }
            if (!isLoaded) {
              node.state.assign({ isLoaded: true, error: void 0 });
            }
          }
        }
        disposes.forEach((fn) => fn());
        disposes = [];
        nodes == null ? void 0 : nodes.forEach(({ node: node2, track }) => {
          disposes.push(onChange(node2, markDirty, { immediate: true, trackingType: track }));
        });
      }
      e.cancel = true;
    },
    { fromComputed: true }
  );
  node.activatedObserveDispose = () => {
    observeDispose == null ? void 0 : observeDispose();
    disposes.forEach((fn) => fn());
  };
  return activatedValue;
}
function activateNodeBase(node, value) {
  if (!node.state) {
    node.state = createObservable(
      {
        isLoaded: false
      },
      false,
      extractPromise,
      getProxy
    );
  }
  if (node.activationState) {
    const { set: setFn, get: getFn, initial } = node.activationState;
    value = getFn == null ? void 0 : getFn();
    if (value == void 0 || value === null) {
      value = initial;
    }
    if (setFn) {
      let allChanges = [];
      let latestValue = void 0;
      let runNumber = 0;
      const runChanges = (listenerParams) => {
        if (allChanges.length > 0) {
          let changes;
          let value2;
          let isFromPersist = false;
          let isFromSync = false;
          let getPrevious;
          if (listenerParams) {
            changes = listenerParams.changes;
            value2 = listenerParams.value;
            isFromPersist = listenerParams.isFromPersist;
            isFromSync = listenerParams.isFromSync;
            getPrevious = listenerParams.getPrevious;
          } else {
            changes = allChanges;
            value2 = latestValue;
            getPrevious = createPreviousHandler(value2, changes);
          }
          allChanges = [];
          latestValue = void 0;
          globalState.pendingNodes.delete(node);
          runNumber++;
          const thisRunNumber = runNumber;
          const run = () => {
            if (thisRunNumber !== runNumber) {
              return;
            }
            node.isComputing = true;
            setFn({
              value: value2,
              changes,
              isFromPersist,
              isFromSync,
              getPrevious
            });
            node.isComputing = false;
          };
          whenReady(node.state.isLoaded, run);
        }
      };
      const onChangeImmediate = ({ value: value2, changes }) => {
        if (!node.isComputing) {
          if (changes.length > 1 || !isFunction(changes[0].prevAtPath)) {
            latestValue = value2;
            if (allChanges.length > 0) {
              changes = changes.filter((change) => !isArraySubset(allChanges[0].path, change.path));
            }
            allChanges.push(...changes);
            globalState.pendingNodes.set(node, runChanges);
          }
        }
      };
      onChange(node, onChangeImmediate, { immediate: true });
      onChange(node, runChanges);
    }
  }
  const update = ({ value: value2 }) => {
    if (!node.isComputing) {
      node.isComputing = true;
      set(node, value2);
      node.isComputing = false;
    }
  };
  return { update, value };
}
function setToObservable(node, value) {
  var _a;
  const linkedNode = value ? getNode(value) : void 0;
  if (linkedNode !== node && (linkedNode == null ? void 0 : linkedNode.linkedToNode) !== node) {
    node.linkedToNode = linkedNode;
    (_a = node.linkedToNodeDispose) == null ? void 0 : _a.call(node);
    if (linkedNode) {
      linkedNode.linkedFromNodes || (linkedNode.linkedFromNodes = /* @__PURE__ */ new Set());
      linkedNode.linkedFromNodes.add(node);
      node.linkedToNodeDispose = onChange(
        linkedNode,
        () => {
          value = peekInternal(linkedNode);
          if (!isFunction(value)) {
            set(node, value);
          }
        },
        { initial: true },
        /* @__PURE__ */ new Set([node])
      );
    }
  }
  return value;
}
function recursivelyAutoActivate(obj, node) {
  if (!node.recursivelyAutoActivated && (isObject(obj) || isArray(obj)) && !isHintOpaque(obj)) {
    node.recursivelyAutoActivated = true;
    const pathStack = [];
    const getNodeAtPath2 = () => {
      var _a;
      let childNode = node;
      for (let i = 0; i < pathStack.length; i++) {
        const key = pathStack[i];
        const value = (_a = getNodeValue(childNode)) == null ? void 0 : _a[key];
        childNode = getChildNode(childNode, key, isFunction(value) ? value : void 0);
        peekInternal(childNode);
      }
      return childNode;
    };
    recursivelyAutoActivateInner(obj, pathStack, getNodeAtPath2);
  }
}
function recursivelyAutoActivateInner(obj, pathStack, getNodeAtPath2) {
  var _a;
  if ((isObject(obj) || isArray(obj)) && !isHintOpaque(obj) && !isHintPlain(obj)) {
    for (const key in obj) {
      if (hasOwnProperty.call(obj, key)) {
        const value = obj[key];
        if (isObservable(value)) {
          const childNode = getNodeAtPath2();
          extractFunctionOrComputed(childNode, key, value);
          delete childNode.lazy;
        } else {
          const linkedOptions = isFunction(value) && ((_a = value.prototype) == null ? void 0 : _a[symbolLinked]);
          if (linkedOptions) {
            const activate = linkedOptions.activate;
            if (!activate || activate === "auto") {
              const childNode = getNodeAtPath2();
              peek(getChildNode(childNode, key, value));
            }
          }
        }
        if (typeof value === "object") {
          pathStack.push(key);
          recursivelyAutoActivateInner(value, pathStack, getNodeAtPath2);
          pathStack.pop();
        }
      }
    }
  }
}

// src/ObservablePrimitive.ts
var fns = ["get", "set", "peek", "onChange", "toggle"];
function ObservablePrimitiveClass(node) {
  this._node = node;
  for (let i = 0; i < fns.length; i++) {
    const key = fns[i];
    this[key] = this[key].bind(this);
  }
}
function proto(key, fn) {
  ObservablePrimitiveClass.prototype[key] = function(...args) {
    return fn.call(this, this._node, ...args);
  };
}
proto("peek", (node) => {
  flushPending();
  return peek(node);
});
proto("get", (node, options) => {
  flushPending();
  return get(node, options);
});
proto("set", set);
proto("onChange", onChange);
Object.defineProperty(ObservablePrimitiveClass.prototype, symbolGetNode, {
  configurable: true,
  get() {
    return this._node;
  }
});
Object.defineProperty(ObservablePrimitiveClass.prototype, symbolToPrimitive, {
  configurable: true,
  value(hint) {
    return toPrimitive(this._node, hint);
  }
});
ObservablePrimitiveClass.prototype.toggle = function() {
  const value = this.peek();
  if (value === void 0 || value === null || isBoolean(value)) {
    this.set(!value);
  } else if (process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test") {
    throw new Error("[legend-state] Cannot toggle a non-boolean value");
  }
};
ObservablePrimitiveClass.prototype.delete = function() {
  this.set(void 0);
  return this;
};

// src/observable.ts
function observable(value) {
  return createObservable(value, false, extractPromise, getProxy, ObservablePrimitiveClass);
}
function observablePrimitive(value) {
  return createObservable(value, true, extractPromise, getProxy, ObservablePrimitiveClass);
}

// src/computed.ts
function computed(get2, set2) {
  return observable(
    set2 ? linked({ get: get2, set: ({ value }) => set2(value) }) : get2
  );
}

// src/event.ts
function event() {
  const obs = observable(0);
  const node = getNode(obs);
  node.isEvent = true;
  return {
    fire: function() {
      obs.set((v) => v + 1);
    },
    on: function(cb) {
      return obs.onChange(cb);
    },
    get: function() {
      return obs.get();
    },
    // @ts-expect-error eslint doesn't like adding symbols to the object but this does work
    [symbolGetNode]: node
  };
}

// src/proxy.ts
function proxy(get2, set2) {
  return observable(
    (key) => set2 ? linked({
      get: () => get2(key),
      set: ({ value }) => set2(key, value)
    }) : get2(key)
  );
}

// src/syncState.ts
function syncState(obs) {
  const node = getNode(obs);
  if (!node.state) {
    node.state = observable(
      ObservableHint.plain({
        isPersistLoaded: false,
        isLoaded: false,
        isPersistEnabled: true,
        isSyncEnabled: true,
        isGetting: false,
        isSetting: false,
        numPendingGets: 0,
        numPendingSets: 0,
        syncCount: 0,
        resetPersistence: void 0,
        reset: () => Promise.resolve(),
        sync: () => {
          var _a;
          obs.peek();
          if ((_a = node.state) == null ? void 0 : _a.isGetting.peek()) {
            return when(node.state.isLoaded);
          }
          return Promise.resolve();
        },
        getPendingChanges: () => ({}),
        // TODOV3 remove
        clearPersist: void 0
      })
    );
  }
  return node.state;
}

// index.ts
var internal = {
  createPreviousHandler,
  clone,
  deactivateNode,
  deepMerge,
  ensureNodeValue,
  findIDKey,
  get,
  getChildNode,
  getKeys,
  getNode,
  getNodeValue,
  getPathType,
  getProxy,
  getValueAtPath,
  globalState,
  initializePathType,
  ObservablePrimitiveClass,
  observableProperties,
  observableFns,
  optimized,
  peek,
  reactivateNode,
  registerMiddleware,
  safeParse,
  safeStringify,
  set,
  setAtPath,
  setNodeValue,
  symbolLinked,
  symbolDelete,
  tracking
};

export { ObservableHint, ObservablePrimitiveClass, applyChange, applyChanges, batch, beginBatch, beginTracking, computeSelector, computed, constructObjectWithPath, deconstructObjectWithPath, endBatch, endTracking, event, findIDKey, getNode, getNodeValue, getObservableIndex, hasOwnProperty, internal, isArray, isBoolean, isDate, isEmpty, isFunction, isMap, isNullOrUndefined, isNumber, isObject, isObservable, isObservableValueReady, isObserved, isPlainObject, isPrimitive, isPromise, isSet, isString, isSymbol, linked, mergeIntoObservable, observable, observablePrimitive, observe, opaqueObject2 as opaqueObject, optimized, proxy, setAtPath, setSilently, setupTracking, shouldIgnoreUnobserved, symbolDelete, syncState, trackSelector, tracking, updateTracking, when, whenReady };
