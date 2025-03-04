# Copyright 2018 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Adagrad optimizer"""

import numpy as np

from pennylane.utils import _flatten, unflatten
from .gradient_descent import GradientDescentOptimizer


class AdagradOptimizer(GradientDescentOptimizer):
    r"""Gradient-descent optimizer with past-gradient-dependent
    learning rate in each dimension.

    Adagrad adjusts the learning rate for each parameter :math:`x_i`
    in :math:`x` based on past gradients. We therefore have to consider
    each parameter update individually,

    .. math::
        x^{(t+1)}_i = x^{(t)}_i - \eta_i^{(t+1)} \partial_{w_i} f(x^{(t)}),

    where the gradient is replaced by a (scalar) partial derivative.

    The learning rate in step :math:`t` is given by

    .. math::
        \eta_i^{(t+1)} = \frac{ \eta_{\mathrm{init}} }{ \sqrt{a_i^{(t+1)} + \epsilon } },
        ~~~ a_i^{(t+1)} = \sum_{k=1}^t (\partial_{x_i} f(x^{(k)}))^2.

    The offset :math:`\epsilon` avoids division by zero.

    :math:`\eta` is the step size, a user defined parameter.

    Args:
        stepsize (float): the user-defined hyperparameter :math:`\eta`
        eps (float): offset :math:`\epsilon` added for numerical stability
    """
    def __init__(self, stepsize=0.01, eps=1e-8):
        super().__init__(stepsize)
        self.eps = eps
        self.accumulation = None

    def apply_grad(self, grad, x):
        r"""Update the variables x to take a single optimization step. Flattens and unflattens
        the inputs to maintain nested iterables as the parameters of the optimization.

        Args:
            grad (array): The gradient of the objective
                function at point :math:`x^{(t)}`: :math:`\nabla f(x^{(t)})`
            x (array): the current value of the variables :math:`x^{(t)}`

        Returns:
            array: the new values :math:`x^{(t+1)}`
        """

        x_flat = _flatten(x)
        grad_flat = list(_flatten(grad))

        if self.accumulation is None:
            self.accumulation = [g*g for g in grad_flat]
        else:
            self.accumulation = [a + g*g for a, g in zip(self.accumulation, grad_flat)]

        x_new_flat = [e - (self._stepsize / np.sqrt(a + self.eps)) * g for a, g, e in zip(self.accumulation, grad_flat, x_flat)]

        return unflatten(x_new_flat, x)

    def reset(self):
        """Reset optimizer by erasing memory of past steps."""
        self.accumulation = None
