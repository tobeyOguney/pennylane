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
"""
Unit tests for the :mod:`pennylane.plugin.DefaultQubit` device.
"""
import cmath
# pylint: disable=protected-access,cell-var-from-loop
import math

import pytest
import pennylane as qml
from pennylane import numpy as np

tensornetwork = pytest.importorskip("tensornetwork", minversion="0.1")


U = np.array(
    [
        [0.83645892 - 0.40533293j, -0.20215326 + 0.30850569j],
        [-0.23889780 - 0.28101519j, -0.88031770 - 0.29832709j],
    ]
)


U2 = np.array(
    [
        [
            -0.07843244 - 3.57825948e-01j,
            0.71447295 - 5.38069384e-02j,
            0.20949966 + 6.59100734e-05j,
            -0.50297381 + 2.35731613e-01j,
        ],
        [
            -0.26626692 + 4.53837083e-01j,
            0.27771991 - 2.40717436e-01j,
            0.41228017 - 1.30198687e-01j,
            0.01384490 - 6.33200028e-01j,
        ],
        [
            -0.69254712 - 2.56963068e-02j,
            -0.15484858 + 6.57298384e-02j,
            -0.53082141 + 7.18073414e-02j,
            -0.41060450 - 1.89462315e-01j,
        ],
        [
            -0.09686189 - 3.15085273e-01j,
            -0.53241387 - 1.99491763e-01j,
            0.56928622 + 3.97704398e-01j,
            -0.28671074 - 6.01574497e-02j,
        ],
    ]
)


U_toffoli = np.diag([1 for i in range(8)])
U_toffoli[6:8, 6:8] = np.array([[0, 1], [1, 0]])

U_swap = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]])

U_cswap = np.array([[1, 0, 0, 0, 0, 0, 0, 0],
                    [0, 1, 0, 0, 0, 0, 0, 0],
                    [0, 0, 1, 0, 0, 0, 0, 0],
                    [0, 0, 0, 1, 0, 0, 0, 0],
                    [0, 0, 0, 0, 1, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 1, 0],
                    [0, 0, 0, 0, 0, 1, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0, 1]])


H = np.array(
    [[1.02789352, 1.61296440 - 0.3498192j], [1.61296440 + 0.3498192j, 1.23920938 + 0j]]
)


THETA = np.linspace(0.11, 1, 3)
PHI = np.linspace(0.32, 1, 3)
VARPHI = np.linspace(0.02, 1, 3)


def prep_par(par, op):
    "Convert par into a list of parameters that op expects."
    if op.par_domain == "A":
        return [np.diag([x, 1]) for x in par]
    return par

class TestMaps:
    """Tests the maps for operations and observables."""

    def test_operation_map(self, tensornet_device_3_wires):
        """Test that default qubit device supports all PennyLane discrete gates."""

        assert set(qml.ops._qubit__ops__) ==  set(tensornet_device_3_wires._operation_map)

    def test_observable_map(self, tensornet_device_3_wires):
        """Test that default qubit device supports all PennyLane discrete observables."""

        assert set(qml.ops._qubit__obs__) | {"Identity"} == set(tensornet_device_3_wires._observable_map)


class TestTensornetIntegration:
    """Integration tests for expt.tensornet. This test ensures it integrates
    properly with the PennyLane interface, in particular QNode."""

    def test_load_tensornet_device(self):
        """Test that the tensor network plugin loads correctly"""

        dev = qml.device("expt.tensornet", wires=2)
        assert dev.num_wires == 2
        assert dev.shots == 1
        assert dev.analytic
        assert dev.short_name == "expt.tensornet"

    def test_args(self):
        """Test that the plugin requires correct arguments"""

        with pytest.raises(
            TypeError, match="missing 1 required positional argument: 'wires'"
        ):
            qml.device("expt.tensornet")

    @pytest.mark.parametrize("gate", set(qml.ops.cv.ops))
    def test_unsupported_gate_error(self, tensornet_device_3_wires, gate):
        """Tests that an error is raised if an unsupported gate is applied"""
        op = getattr(qml.ops, gate)

        if op.num_wires is qml.operation.Wires.Any or qml.operation.Wires.All:
            wires = [0]
        else:
            wires = list(range(op.num_wires))

        @qml.qnode(tensornet_device_3_wires)
        def circuit(*x):
            """Test quantum function"""
            x = prep_par(x, op)
            op(*x, wires=wires)

            return qml.expval(qml.X(0))

        with pytest.raises(
            qml.DeviceError,
            match="Gate {} not supported on device expt.tensornet".format(gate),
        ):
            x = np.random.random([op.num_params])
            circuit(*x)

    @pytest.mark.parametrize("observable", set(qml.ops.cv.obs))
    def test_unsupported_observable_error(self, tensornet_device_3_wires, observable):
        """Test error is raised with unsupported observables"""

        op = getattr(qml.ops, observable)

        if op.num_wires is qml.operation.Wires.Any or qml.operation.Wires.All:
            wires = [0]
        else:
            wires = list(range(op.num_wires))

        @qml.qnode(tensornet_device_3_wires)
        def circuit(*x):
            """Test quantum function"""
            x = prep_par(x, op)
            return qml.expval(op(*x, wires=wires))

        with pytest.raises(
            qml.DeviceError,
            match="Observable {} not supported on device expt.tensornet".format(observable),
        ):
            x = np.random.random([op.num_params])
            circuit(*x)

    def test_qubit_circuit(self, tensornet_device_1_wire, tol):
        """Test that the tensor network plugin provides correct result for a simple circuit"""

        p = 0.543

        @qml.qnode(tensornet_device_1_wire)
        def circuit(x):
            qml.RX(x, wires=0)
            return qml.expval(qml.PauliY(0))

        expected = -np.sin(p)

        assert np.isclose(circuit(p), expected, atol=tol, rtol=0)

    def test_qubit_identity(self, tensornet_device_1_wire, tol):
        """Test that the tensor network plugin provides correct result for the Identity expectation"""

        p = 0.543

        @qml.qnode(tensornet_device_1_wire)
        def circuit(x):
            """Test quantum function"""
            qml.RX(x, wires=0)
            return qml.expval(qml.Identity(0))

        assert np.isclose(circuit(p), 1, atol=tol, rtol=0)

    # This test is ran against the state |0> with one Z expval
    @pytest.mark.parametrize("name,expected_output", [
        ("PauliX", -1),
        ("PauliY", -1),
        ("PauliZ", 1),
        ("Hadamard", 0),
    ])
    def test_supported_gate_single_wire_no_parameters(self, tensornet_device_1_wire, tol, name, expected_output):
        """Tests supported gates that act on a single wire that are not parameterized"""

        op = getattr(qml.ops, name)

        assert tensornet_device_1_wire.supports_operation(name)

        @qml.qnode(tensornet_device_1_wire)
        def circuit():
            op(wires=0)
            return qml.expval(qml.PauliZ(0))

        assert np.isclose(circuit(), expected_output, atol=tol, rtol=0)

    # This test is ran against the state |Phi+> with two Z expvals
    @pytest.mark.parametrize("name,expected_output", [
        ("CNOT", [-1/2, 1]),
        ("SWAP", [-1/2, -1/2]),
        ("CZ", [-1/2, -1/2]),
    ])
    def test_supported_gate_two_wires_no_parameters(self, tensornet_device_2_wires, tol, name, expected_output):
        """Tests supported gates that act on two wires that are not parameterized"""

        op = getattr(qml.ops, name)

        assert tensornet_device_2_wires.supports_operation(name)

        @qml.qnode(tensornet_device_2_wires)
        def circuit():
            qml.QubitStateVector(np.array([1/2, 0, 0, math.sqrt(3)/2]), wires=[0, 1])
            op(wires=[0, 1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        assert np.allclose(circuit(), expected_output, atol=tol, rtol=0)

    @pytest.mark.parametrize("name,expected_output", [
        ("CSWAP", [-1, -1, 1]),
    ])
    def test_supported_gate_three_wires_no_parameters(self, tensornet_device_3_wires, tol, name, expected_output):
        """Tests supported gates that act on three wires that are not parameterized"""

        op = getattr(qml.ops, name)

        assert tensornet_device_3_wires.supports_operation(name)

        @qml.qnode(tensornet_device_3_wires)
        def circuit():
            qml.BasisState(np.array([1, 0, 1]), wires=[0, 1, 2])
            op(wires=[0, 1, 2])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1)), qml.expval(qml.PauliZ(2))

        assert np.allclose(circuit(), expected_output, atol=tol, rtol=0)

    # This test is ran with two Z expvals
    @pytest.mark.parametrize("name,par,expected_output", [
        ("BasisState", [0, 0], [1, 1]),
        ("BasisState", [1, 0], [-1, 1]),
        ("BasisState", [0, 1], [1, -1]),
        ("QubitStateVector", [1, 0, 0, 0], [1, 1]),
        ("QubitStateVector", [0, 0, 1, 0], [-1, 1]),
        ("QubitStateVector", [0, 1, 0, 0], [1, -1]),
    ])
    def test_supported_state_preparation(self, tensornet_device_2_wires, tol, name, par, expected_output):
        """Tests supported state preparations"""

        op = getattr(qml.ops, name)

        assert tensornet_device_2_wires.supports_operation(name)

        @qml.qnode(tensornet_device_2_wires)
        def circuit():
            op(np.array(par), wires=[0, 1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        assert np.allclose(circuit(), expected_output, atol=tol, rtol=0)

    # This test is ran on the state |0> with one Z expvals
    @pytest.mark.parametrize("name,par,expected_output", [
        ("PhaseShift", [math.pi/2], 1),
        ("PhaseShift", [-math.pi/4], 1),
        ("RX", [math.pi/2], 0),
        ("RX", [-math.pi/4], 1/math.sqrt(2)),
        ("RY", [math.pi/2], 0),
        ("RY", [-math.pi/4], 1/math.sqrt(2)),
        ("RZ", [math.pi/2], 1),
        ("RZ", [-math.pi/4], 1),
        ("Rot", [math.pi/2, 0, 0], 1),
        ("Rot", [0, math.pi/2, 0], 0),
        ("Rot", [0, 0, math.pi/2], 1),
        ("Rot", [math.pi/2, -math.pi/4, -math.pi/4], 1/math.sqrt(2)),
        ("Rot", [-math.pi/4, math.pi/2, math.pi/4], 0),
        ("Rot", [-math.pi/4, math.pi/4, math.pi/2], 1/math.sqrt(2)),
        ("QubitUnitary", [np.array([[1j/math.sqrt(2), 1j/math.sqrt(2)], [1j/math.sqrt(2), -1j/math.sqrt(2)]])], 0),
        ("QubitUnitary", [np.array([[-1j/math.sqrt(2), 1j/math.sqrt(2)], [1j/math.sqrt(2), 1j/math.sqrt(2)]])], 0),
    ])
    def test_supported_gate_single_wire_with_parameters(self, tensornet_device_1_wire, tol, name, par, expected_output):
        """Tests supported gates that act on a single wire that are parameterized"""

        op = getattr(qml.ops, name)

        assert tensornet_device_1_wire.supports_operation(name)

        @qml.qnode(tensornet_device_1_wire)
        def circuit():
            op(*par, wires=0)
            return qml.expval(qml.PauliZ(0))

        assert np.isclose(circuit(), expected_output, atol=tol, rtol=0)

    # This test is ran against the state 1/2|00>+sqrt(3)/2|11> with two Z expvals
    @pytest.mark.parametrize("name,par,expected_output", [
        ("CRX", [0], [-1/2, -1/2]),
        ("CRX", [-math.pi], [-1/2, 1]),
        ("CRX", [math.pi/2], [-1/2, 1/4]),
        ("CRY", [0], [-1/2, -1/2]),
        ("CRY", [-math.pi], [-1/2, 1]),
        ("CRY", [math.pi/2], [-1/2, 1/4]),
        ("CRZ", [0], [-1/2, -1/2]),
        ("CRZ", [-math.pi], [-1/2, -1/2]),
        ("CRZ", [math.pi/2], [-1/2, -1/2]),
        ("CRot", [math.pi/2, 0, 0], [-1/2, -1/2]),
        ("CRot", [0, math.pi/2, 0], [-1/2, 1/4]),
        ("CRot", [0, 0, math.pi/2], [-1/2, -1/2]),
        ("CRot", [math.pi/2, 0, -math.pi], [-1/2, -1/2]),
        ("CRot", [0, math.pi/2, -math.pi], [-1/2, 1/4]),
        ("CRot", [-math.pi, 0, math.pi/2], [-1/2, -1/2]),
        ("QubitUnitary", [np.array([[1, 0, 0, 0], [0, 1/math.sqrt(2), 1/math.sqrt(2), 0], [0, 1/math.sqrt(2), -1/math.sqrt(2), 0], [0, 0, 0, 1]])], [-1/2, -1/2]),
        ("QubitUnitary", [np.array([[-1, 0, 0, 0], [0, 1/math.sqrt(2), 1/math.sqrt(2), 0], [0, 1/math.sqrt(2), -1/math.sqrt(2), 0], [0, 0, 0, -1]])], [-1/2, -1/2]),
    ])
    def test_supported_gate_two_wires_with_parameters(self, tensornet_device_2_wires, tol, name, par, expected_output):
        """Tests supported gates that act on two wires wires that are parameterized"""

        op = getattr(qml.ops, name)

        assert tensornet_device_2_wires.supports_operation(name)

        @qml.qnode(tensornet_device_2_wires)
        def circuit():
            qml.QubitStateVector(np.array([1/2, 0, 0, math.sqrt(3)/2]), wires=[0, 1])
            op(*par, wires=[0, 1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        assert np.allclose(circuit(), expected_output, atol=tol, rtol=0)

    @pytest.mark.parametrize("name,state,expected_output", [
        ("PauliX", [1/math.sqrt(2), 1/math.sqrt(2)], 1),
        ("PauliX", [1/math.sqrt(2), -1/math.sqrt(2)], -1),
        ("PauliX", [1, 0], 0),
        ("PauliY", [1/math.sqrt(2), 1j/math.sqrt(2)], 1),
        ("PauliY", [1/math.sqrt(2), -1j/math.sqrt(2)], -1),
        ("PauliY", [1, 0], 0),
        ("PauliZ", [1, 0], 1),
        ("PauliZ", [0, 1], -1),
        ("PauliZ", [1/math.sqrt(2), 1/math.sqrt(2)], 0),
        ("Hadamard", [1, 0], 1/math.sqrt(2)),
        ("Hadamard", [0, 1], -1/math.sqrt(2)),
        ("Hadamard", [1/math.sqrt(2), 1/math.sqrt(2)], 1/math.sqrt(2)),
    ])
    def test_supported_observable_single_wire_no_parameters(self, tensornet_device_1_wire, tol, name, state, expected_output):
        """Tests supported observables on single wires without parameters."""

        obs = getattr(qml.ops, name)

        assert tensornet_device_1_wire.supports_observable(name)

        @qml.qnode(tensornet_device_1_wire)
        def circuit():
            qml.QubitStateVector(np.array(state), wires=[0])
            return qml.expval(obs(wires=[0]))

        assert np.isclose(circuit(), expected_output, atol=tol, rtol=0)

    @pytest.mark.parametrize("name,state,expected_output,par", [
        ("Identity", [1, 0], 1, []),
        ("Identity", [0, 1], 1, []),
        ("Identity", [1/math.sqrt(2), -1/math.sqrt(2)], 1, []),
        ("Hermitian", [1, 0], 1, [np.array([[1, 1j], [-1j, 1]])]),
        ("Hermitian", [0, 1], 1, [np.array([[1, 1j], [-1j, 1]])]),
        ("Hermitian", [1/math.sqrt(2), -1/math.sqrt(2)], 1, [np.array([[1, 1j], [-1j, 1]])]),
    ])
    def test_supported_observable_single_wire_with_parameters(self, tensornet_device_1_wire, tol, name, state, expected_output, par):
        """Tests supported observables on single wires with parameters."""

        obs = getattr(qml.ops, name)

        assert tensornet_device_1_wire.supports_observable(name)

        @qml.qnode(tensornet_device_1_wire)
        def circuit():
            qml.QubitStateVector(np.array(state), wires=[0])
            return qml.expval(obs(*par, wires=[0]))

        assert np.isclose(circuit(), expected_output, atol=tol, rtol=0)

    @pytest.mark.parametrize("name,state,expected_output,par", [
        ("Hermitian", [1/math.sqrt(3), 0, 1/math.sqrt(3), 1/math.sqrt(3)], 5/3, [np.array([[1, 1j, 0, 1], [-1j, 1, 0, 0], [0, 0, 1, -1j], [1, 0, 1j, 1]])]),
        ("Hermitian", [0, 0, 0, 1], 0, [np.array([[0, 1j, 0, 0], [-1j, 0, 0, 0], [0, 0, 0, -1j], [0, 0, 1j, 0]])]),
        ("Hermitian", [1/math.sqrt(2), 0, -1/math.sqrt(2), 0], 1, [np.array([[1, 1j, 0, 0], [-1j, 1, 0, 0], [0, 0, 1, -1j], [0, 0, 1j, 1]])]),
        ("Hermitian", [1/math.sqrt(3), -1/math.sqrt(3), 1/math.sqrt(6), 1/math.sqrt(6)], 1, [np.array([[1, 1j, 0, .5j], [-1j, 1, 0, 0], [0, 0, 1, -1j], [-.5j, 0, 1j, 1]])]),
        ("Hermitian", [1/math.sqrt(2), 0, 0, 1/math.sqrt(2)], 1, [np.array([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, -1, 0], [0, 0, 0, 1]])]),
        ("Hermitian", [0, 1/math.sqrt(2), -1/math.sqrt(2), 0], -1, [np.array([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, -1, 0], [0, 0, 0, 1]])]),
    ])
    def test_supported_observable_two_wires_with_parameters(self, tensornet_device_2_wires, tol, name, state, expected_output, par):
        """Tests supported observables on two wires with parameters."""

        obs = getattr(qml.ops, name)

        assert tensornet_device_2_wires.supports_observable(name)

        @qml.qnode(tensornet_device_2_wires)
        def circuit():
            qml.QubitStateVector(np.array(state), wires=[0, 1])
            return qml.expval(obs(*par, wires=[0, 1]))

        assert np.isclose(circuit(), expected_output, atol=tol, rtol=0)

    def test_expval_warnings(self):
        """Tests that expval raises a warning if the given observable is complex."""

        dev = qml.device("expt.tensornet", wires=1)

        A = np.array([[2j, 1j], [-3j, 1j]])
        obs_node = dev._add_node(A, wires=[0])

        # text warning raised if matrix is complex
        with pytest.warns(RuntimeWarning, match='Nonvanishing imaginary part'):
            dev.ev([obs_node], wires=[[0]])

    def test_cannot_overwrite_state(self, tensornet_device_2_wires):
        """Tests that _state is a property and cannot be overwritten."""

        dev = tensornet_device_2_wires

        with pytest.raises(AttributeError, match="can't set attribute"):
            dev._state = np.array([[1, 0],
                                   [0, 0]])

    def test_correct_state(self, tensornet_device_2_wires):

        dev = tensornet_device_2_wires
        state = dev._state

        expected = np.array([[1, 0],
                             [0, 0]])
        assert np.allclose(state, expected)

        @qml.qnode(dev)
        def circuit():
            qml.Hadamard(wires=0)
            return qml.expval(qml.PauliZ(0))

        circuit()
        state = dev._state

        expected = np.array([[1, 0],
                             [1, 0]]) / np.sqrt(2)
        assert np.allclose(state, expected)


@pytest.mark.parametrize("theta,phi,varphi", list(zip(THETA, PHI, VARPHI)))
class TestTensorExpval:
    """Test tensor expectation values"""

    def test_paulix_pauliy(self, theta, phi, varphi, tol):
        """Test that a tensor product involving PauliX and PauliY works correctly"""
        dev = qml.device("expt.tensornet", wires=3)
        dev.reset()

        dev.apply("RX", wires=[0], par=[theta])
        dev.apply("RX", wires=[1], par=[phi])
        dev.apply("RX", wires=[2], par=[varphi])
        dev.apply("CNOT", wires=[0, 1], par=[])
        dev.apply("CNOT", wires=[1, 2], par=[])

        res = dev.expval(["PauliX", "PauliY"], [[0], [2]], [[], []])
        expected = np.sin(theta) * np.sin(phi) * np.sin(varphi)

        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_pauliz_identity(self, theta, phi, varphi, tol):
        """Test that a tensor product involving PauliZ and Identity works correctly"""
        dev = qml.device("expt.tensornet", wires=3)
        dev.reset()
        dev.apply("RX", wires=[0], par=[theta])
        dev.apply("RX", wires=[1], par=[phi])
        dev.apply("RX", wires=[2], par=[varphi])
        dev.apply("CNOT", wires=[0, 1], par=[])
        dev.apply("CNOT", wires=[1, 2], par=[])

        res = dev.expval(["PauliZ", "Identity", "PauliZ"], [[0], [1], [2]], [[], [], []])
        expected = np.cos(varphi)*np.cos(phi)

        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_pauliz_hadamard(self, theta, phi, varphi, tol):
        """Test that a tensor product involving PauliZ and PauliY and hadamard works correctly"""
        dev = qml.device("expt.tensornet", wires=3)
        dev.reset()
        dev.apply("RX", wires=[0], par=[theta])
        dev.apply("RX", wires=[1], par=[phi])
        dev.apply("RX", wires=[2], par=[varphi])
        dev.apply("CNOT", wires=[0, 1], par=[])
        dev.apply("CNOT", wires=[1, 2], par=[])

        res = dev.expval(["PauliZ", "Hadamard", "PauliY"], [[0], [1], [2]], [[], [], []])
        expected = -(np.cos(varphi) * np.sin(phi) + np.sin(varphi) * np.cos(theta)) / np.sqrt(2)

        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_hermitian(self, theta, phi, varphi, tol):
        """Test that a tensor product involving qml.Hermitian works correctly"""
        dev = qml.device("expt.tensornet", wires=3)
        dev.reset()
        dev.apply("RX", wires=[0], par=[theta])
        dev.apply("RX", wires=[1], par=[phi])
        dev.apply("RX", wires=[2], par=[varphi])
        dev.apply("CNOT", wires=[0, 1], par=[])
        dev.apply("CNOT", wires=[1, 2], par=[])

        A = np.array(
            [
                [-6, 2 + 1j, -3, -5 + 2j],
                [2 - 1j, 0, 2 - 1j, -5 + 4j],
                [-3, 2 + 1j, 0, -4 + 3j],
                [-5 - 2j, -5 - 4j, -4 - 3j, -6],
            ]
        )

        res = dev.expval(["PauliZ", "Hermitian"], [[0], [1, 2]], [[], [A]])
        expected = 0.5 * (
            -6 * np.cos(theta) * (np.cos(varphi) + 1)
            - 2 * np.sin(varphi) * (np.cos(theta) + np.sin(phi) - 2 * np.cos(phi))
            + 3 * np.cos(varphi) * np.sin(phi)
            + np.sin(phi)
        )

        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_hermitian_hermitian(self, theta, phi, varphi, tol):
        """Test that a tensor product involving two Hermitian matrices works correctly"""
        dev = qml.device("expt.tensornet", wires=3)
        dev.reset()
        dev.apply("RX", wires=[0], par=[theta])
        dev.apply("RX", wires=[1], par=[phi])
        dev.apply("RX", wires=[2], par=[varphi])
        dev.apply("CNOT", wires=[0, 1], par=[])
        dev.apply("CNOT", wires=[1, 2], par=[])

        A1 = np.array([[1, 2],
                       [2, 4]])

        A2 = np.array(
            [
                [-6, 2 + 1j, -3, -5 + 2j],
                [2 - 1j, 0, 2 - 1j, -5 + 4j],
                [-3, 2 + 1j, 0, -4 + 3j],
                [-5 - 2j, -5 - 4j, -4 - 3j, -6],
            ]
        )

        res = dev.expval(["Hermitian", "Hermitian"], [[0], [1, 2]], [[A1], [A2]])
        expected = 0.25 * (
            -30
            + 4 * np.cos(phi) * np.sin(theta)
            + 3 * np.cos(varphi) * (-10 + 4 * np.cos(phi) * np.sin(theta) - 3 * np.sin(phi))
            - 3 * np.sin(phi)
            - 2 * (5 + np.cos(phi) * (6 + 4 * np.sin(theta)) + (-3 + 8 * np.sin(theta)) * np.sin(phi))
            * np.sin(varphi)
            + np.cos(theta)
            * (
                18
                + 5 * np.sin(phi)
                + 3 * np.cos(varphi) * (6 + 5 * np.sin(phi))
                + 2 * (3 + 10 * np.cos(phi) - 5 * np.sin(phi)) * np.sin(varphi)
            )
        )

        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_hermitian_identity_expectation(self, theta, phi, varphi, tol):
        """Test that a tensor product involving an Hermitian matrix and the identity works correctly"""
        dev = qml.device("expt.tensornet", wires=2)
        dev.reset()
        dev.apply("RY", wires=[0], par=[theta])
        dev.apply("RY", wires=[1], par=[phi])
        dev.apply("CNOT", wires=[0, 1], par=[])

        A = np.array([[1.02789352, 1.61296440 - 0.3498192j], [1.61296440 + 0.3498192j, 1.23920938 + 0j]])

        res = dev.expval(["Hermitian", "Identity"], [[0], [1]], [[A], []])

        a = A[0, 0]
        re_b = A[0, 1].real
        d = A[1, 1]
        expected = ((a - d) * np.cos(theta) + 2 * re_b * np.sin(theta) * np.sin(phi) + a + d) / 2

        assert np.allclose(res, expected, atol=tol, rtol=0)
