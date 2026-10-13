#!/usr/bin/env node
/**
 * patch-darwin-x64.mjs
 *
 * Ensures `@huggingface/transformers` + `onnxruntime-node` works seamlessly on
 * macOS Intel (`darwin/x64`) where Microsoft dropped native napi-v6 binaries in
 * onnxruntime 1.21+:
 * 1. Redirects `onnxruntime-node` to `onnxruntime-web` multi-threaded SIMD WASM
 *    when `bin/napi-v6/darwin/x64/onnxruntime_binding.node` is absent.
 * 2. Patches `transformers.node.mjs` so `getCoreModelFile` and `getModelDataFiles`
 *    pass `Uint8Array` buffers (`externalData`) when running on WASM in Node.js.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const ortIndexPath = path.join(__dirname, "node_modules/onnxruntime-node/dist/index.js");
if (fs.existsSync(ortIndexPath)) {
  const ortShim = `"use strict";
const fs = require("fs");
const path = require("path");

const nativeBindingPath = path.join(
  __dirname,
  "..",
  "bin",
  "napi-v6",
  process.platform,
  process.arch,
  "onnxruntime_binding.node"
);

if (fs.existsSync(nativeBindingPath)) {
  var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
      if (k2 === undefined) k2 = k;
      var desc = Object.getOwnPropertyDescriptor(m, k);
      if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
        desc = { enumerable: true, get: function() { return m[k]; } };
      }
      Object.defineProperty(o, k2, desc);
  }) : (function(o, m, k, k2) {
      if (k2 === undefined) k2 = k;
      o[k2] = m[k];
  }));
  var __exportStar = (this && this.__exportStar) || function(m, exports) {
      for (var p in m) if (p !== "default" && !Object.prototype.hasOwnProperty.call(exports, p)) __createBinding(exports, m, p);
  };
  Object.defineProperty(exports, "__esModule", { value: true });
  exports.listSupportedBackends = void 0;
  __exportStar(require("onnxruntime-common"), exports);
  var backend_1 = require("./backend");
  Object.defineProperty(exports, "listSupportedBackends", { enumerable: true, get: function () { return backend_1.listSupportedBackends; } });
  const onnxruntime_common_1 = require("onnxruntime-common");
  const version_1 = require("./version");
  const backend_2 = require("./backend");
  const backends = (0, backend_2.listSupportedBackends)();
  for (const backend of backends) {
      (0, onnxruntime_common_1.registerBackend)(backend.name, backend_2.onnxruntimeBackend, 100);
  }
  Object.defineProperty(onnxruntime_common_1.env.versions, 'node', { value: version_1.version, enumerable: true });
} else {
  const ortWeb = require("onnxruntime-web");
  ortWeb.env.wasm.numThreads = Math.min(8, require("os").cpus().length);
  ortWeb.env.wasm.wasmPaths = path.dirname(require.resolve("onnxruntime-web")) + "/";
  module.exports = ortWeb;
}
`;
  fs.writeFileSync(ortIndexPath, ortShim, "utf-8");
}

const tfNodeMjs = path.join(__dirname, "node_modules/@huggingface/transformers/dist/transformers.node.mjs");
if (fs.existsSync(tfNodeMjs)) {
  let content = fs.readFileSync(tfNodeMjs, "utf-8");
  content = content.replace(
    "return await getModelFile(pretrained_model_name_or_path, fullPath, true, options, apis.IS_NODE_ENV);",
    "return await getModelFile(pretrained_model_name_or_path, fullPath, true, options, !ONNX?.env?.wasm);"
  );
  content = content.replace(
    "const return_path = apis.IS_NODE_ENV;",
    "const return_path = !ONNX?.env?.wasm;"
  );
  fs.writeFileSync(tfNodeMjs, content, "utf-8");
}
