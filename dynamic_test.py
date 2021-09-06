#!/usr/bin/env python3

import pdb
import numpy as np
import torch
import tvm
from tvm import relay
from tvm.relay.frontend.pytorch import from_pytorch
import tvm.testing


class SimpleIf(torch.nn.Module):
    def __init__(self, N, M):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.rand(N, M))

    def forward(self, inp):
        if inp.sum() > 0.:
            output = self.weight + inp
        else:
            output = self.weight - inp
        return output


class NestedIf(torch.nn.Module):
    def __init__(self, N, M):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.rand(N, M))

    def forward(self, inp):
        if inp.sum() > 0.:
            if inp.mean() > 0.:
                output = self.weight + inp
            else:
                output = self.weight - inp
        else:
            if inp.mean() > 0.:
                output = self.weight * inp
            else:
                output = self.weight / inp

        return output


class ScalarLoop(torch.nn.Module):
    def forward(self, inp):
        a = 0
        for i in range(inp.size(0)):
            b = i * i
            b = b + 1
            a += b
        return a


class SimpleLoop(torch.nn.Module):
    def forward(self, inp):
        a = inp
        for i in range(inp.size(0)):
            b = a * 2.
            c = a + b
            a += c
        return a


class LoopWithIf(torch.nn.Module):
    def forward(self, inp):
        a = inp
        for i in range(inp.size(0)):
            b = a * 2.
            b = a + b
            if b.sum() > 0.0:
                a += b
            else:
                a -= b
        return a


class NestedLoop(torch.nn.Module):
    def forward(self, inp):
        a = inp
        for i in range(inp.size(0)):
            b = a * float(i)
            for j in range(inp.size(1)):
                a += b * float(j)
        return a


class SimpleScalarWhileLoop(torch.nn.Module):
    def forward(self, inp):
        a = 1
        i = 0
        while i < inp.size(0):
            a += i
            i += 2
        return a


class SimpleWhileLoop(torch.nn.Module):
    def forward(self, inp):
        a = inp
        i = 0
        while i < inp.size(0):
            a += a * float(i) * 2.0
            i += 1
        return a


models = [
    SimpleIf(10, 20).eval(),
    NestedIf(10, 20).eval(),
    ScalarLoop().eval(),
    SimpleLoop().eval(),
    LoopWithIf().eval(),
    SimpleScalarWhileLoop().eval(),
    SimpleWhileLoop().eval(),
    NestedLoop().eval()
]

for raw_model in models:
    script_module = torch.jit.script(raw_model)
    input_name = "input"
    input_shapes = [(input_name, (10, 20))]
    mod, params = from_pytorch(script_module, input_shapes)

    executor = relay.create_executor("vm", mod=mod, target="llvm")
    # executor = relay.create_executor(
    #     "vm", mod=mod, ctx=tvm.cpu(0), target="llvm")
    evaluator = executor.evaluate()

    for i in range(5):
        inp = torch.rand(input_shapes[0][1], dtype=torch.float)

        with torch.no_grad():
            pt_result = raw_model(inp.clone())

        params[input_name] = inp.numpy()
        op_res = evaluator(**params)
        if not isinstance(pt_result, torch.Tensor):
            tvm_res = np.asscalar(op_res.asnumpy())
            print(abs(pt_result - tvm_res))
            assert pt_result == tvm_res
        else:
            print(np.max(np.abs(op_res.asnumpy() - pt_result.numpy())))
            tvm.testing.assert_allclose(
                op_res.asnumpy(), pt_result.numpy(), rtol=1e-5, atol=1e-5)
