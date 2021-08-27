import unittest
from sequence_generation import topological_sort, intersect, State_Space_Error, \
                Topology, State_Search_Flags, Node, Stateful_Node, Input, Output, PowerState, \
                state_difference, Wire, Constraint
from enzian_descriptions import enzian_nodes, enzian_wires, ISPPAC
import itertools
import random
import copy
from functools import partial
import z3

def compare_unordered_lists(l1, l2):
    if isinstance(l1, tuple) and isinstance(l2, tuple) and len(l1) == len(l2):
        return all(list(map(lambda x: compare_unordered_lists(*x), list(zip(l1, l2)))))
    if isinstance(l1, list) and isinstance(l2, list) and len(l1) == len(l2):
        l2_copy = copy.deepcopy(l2)
        for e1 in l1:
            i = 0
            while i < len(l2_copy):
                if compare_unordered_lists(e1, l2_copy[i]):
                    break
                i = i + 1
            if i < len(l2_copy):
                del l2_copy[i]
            else:
                return False
        return True
    else:
        return l1 == l2



class TestStateDifference(unittest.TestCase):
    def test_state_difference(self):
        states = [
            ([(2, 8), (0, 1), {3, 2, 5}], [(4, 5), (1, 1), {3, 7, 6}]),
            ([(2, 8), {1}], [(4, 5), {0, 1}])
        ] 

        results = [
            [[(2, 3), (0, 1), {3, 2, 5}], [(6, 8), (0, 1), {3, 2, 5}], [(2, 8), (0, 0), {3, 2, 5}], [(2, 8), (0, 1), {2, 5}]],
            [[(2, 3), {1}], [(6, 8), {1}]]
        ]
        for arg, result in list(zip(states, results)):
            #with self.subTest(arg = arg):
            self.assertEqual(state_difference(*arg), result)



class TestTopologicalSort(unittest.TestCase):
    def test_sort(self):
        graph = {"w1": set(), "w2": {"w1"}, "w3": {"w1", "w2"}, "w4": set(), "w5" : {"w4"}}   
        expected = (["w1", "w4"], ["w2", "w5"], ["w3"])
        self.assertTrue(compare_unordered_lists(expected, tuple(topological_sort(graph))))

    def test_not_sortable(self):
        graph = {"w1": set(), "w2": {"w1", "w3"}, "w3": {"w1", "w2"}}
        self.assertIsNone(topological_sort(graph))

class TestIntersect(unittest.TestCase):
    def test_intersect(self):
        arguments_ok = [
            ({0, 1}, {1}),
            ((3, 6), (4, 8)),
            ((2, 3), (3, 5)),
        ]
        arguments_list = map(lambda x:list(x), zip(*arguments_ok))
        arguments_fail = [
            ({0}, {1}),
            ((2, 3), (5, 6))
        ]
        arguments_fail_list = map(lambda x: list(x), zip(*(arguments_ok + arguments_fail)))

        results_ok = [
            {1},
            (4, 6),
            (3, 3)
        ]
        for arg, result in zip(arguments_ok, results_ok):
            #with self.subTest(arg = arg):
            self.assertEqual(intersect(*arg), result)
        self.assertEqual(intersect(*arguments_list), results_ok)
        for arg in arguments_fail:
            #with self.subTest(arg = arg):
            with self.assertRaises(State_Space_Error):
                intersect(*arg)
        with self.assertRaises(State_Space_Error):
            intersect(*arguments_fail_list)

    
class Z3_Test(unittest.TestCase):
    
    def test_recover_solution(self):
        nodes = [("n1", 0x0, Node1, []), ("n2", 0x0, Node2, [])]
        wires = [
            ("w1", "n2", "O1", {("n1", "I1")}),
            ("w2", "n2", "O2", {("n1", "I2")}),
            ("w3", "n2", "O3", {("n1", "I3")})
        ]
        topology = Topology(nodes, wires)
        solution = topology.parametrized_state_search({}, State_Search_Flags(use_z3 = True, visualize = False))
        expected = {"w1": [(5, 5), (44, 44)], "w2": [{0, 1}], "w3": [{3}, {1}]}
        expected_sequence = (["set_w1", "set_w2", "set_w3"], ["w1", "w2", "w3"])
        self.assertEqual(expected, solution[0])
        self.assertTrue(compare_unordered_lists(tuple(solution[3]), expected_sequence))

    def test_param_state_search_unsat(self):
        nodes = [("n1", 0x0, Node1, []), ("n2", 0x0, Node2, [])]
        wires = [
            ("w1", "n2", "O1", {("n1", "I1")}),
            ("w2", "n2", "O2", {("n1", "I2")}),
            ("w3", "n2", "O3", {("n1", "I3")})
        ]
        topology = Topology(nodes, wires)
        solution = topology.parametrized_state_search({"w3": [{4}, {1}]}, State_Search_Flags(use_z3 = True, visualize = False))
        self.assertEqual(solution, [])
    
    def test_translate_state(self):
        topology = Topology([], [])
        topology.most_general_state = {'a' : [{}], 'b': [{}], 'c':[{}], 'd' : [{}]}
        variables = {}
        variables['a'] = z3.Int('a_0')
        variables['b'] = z3.Int('b_0')
        variables['c'] = z3.Int('c_0')
        variables['d'] = z3.Int('d_0')
        state = [(8, 8), {5}, "a", ("a", "c")]
        problem = z3.Solver()
        problem.add(topology.translate_state(state, ['a', 'b', 'c', 'd'], variables))
        self.assertEqual(problem.check(), z3.sat)
        self.assertEqual({"a": [{8}], "b": [{5}], "c": [{8}], "d": [{8}]}, topology.recover_solution(problem.model()))





    
class TestParametrizedStateSearch(unittest.TestCase):
    def test_param_state_search(self):
        node_list = [
            ("psu_motherboard", 0x71, PowerSupply, []),
            ("psu", 0x72, PowerSupply, []),
            ("isppac", 0x55, ISPPAC, ["pac"]),
            ("cpu", 0x01, CPU_3, []),
            ("cpu2", 0x01, CPU2, []),
            ("cpu3", 0x01, CPU2, []),
            ("cpu4", 0x01, CPU2, [])
        ]
        wire_list = \
            [
                ("vdd33", "psu_motherboard", "OUT0", {("cpu", "VDD33")}),
                ("vcc_isppac", "psu_motherboard", "OUT1", {("isppac", "VCC")}),
                ("vcc_in_isppac", "psu_motherboard", "OUT2", {("isppac", "VCC_IN")}),
                ("vdd_cpu/cpu2", "psu", "OUT0", {("cpu", "VDD"), ("cpu2", "VDD")}),
                ("vdd_cpu3", "psu", "OUT1", {("cpu3", "VDD")}),
                ("vdd_cpu4", "psu", "OUT2", {("cpu4", "VDD")}),
                ("en1_cpu/cpu2", "isppac", "OUT0", {("cpu", "EN1"), ("cpu2", "EN1")}),
                ("en2_cpu", "isppac", "OUT1", {("cpu", "EN2")}),
                ("en2_cpu2", "isppac", "OUT2", {("cpu2", "EN2")}),
                ("en1_cpu3/cpu4", "isppac", "OUT3", {("cpu3", "EN1"), ("cpu4", "EN1")}),
                ("en2_cpu3/cpu4", "isppac", "OUT4", {("cpu3", "EN2"), ("cpu4", "EN2")})
            ]
        topolgy = Topology(node_list, wire_list)
        expected = {
            "vdd33": [(0, 0)],  
            "vcc_isppac": [(2800, 3960)], 
            "vcc_in_isppac": [(2250, 5500)], 
            "vdd_cpu/cpu2" : [(0, 0)],
            "vdd_cpu3" : [(0, 0)],
            "vdd_cpu4" : [(0, 0)],
            "en1_cpu/cpu2" : [{0}],
            "en2_cpu" : [{1}],
            "en2_cpu2" : [{0}],
            "en1_cpu3/cpu4" : [{0}],
            "en2_cpu3/cpu4" : [{0}]
            }
        result = topolgy.parametrized_state_search({}, State_Search_Flags(no_output=True, print_solutions=False, advanced_backtracking = False, visualize= False))
        result_backtracking = topolgy.parametrized_state_search({}, State_Search_Flags(no_output=True, print_solutions=False, advanced_backtracking=True, visualize = False))
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result_backtracking), 1)
        self.assertEqual(result[0][0], expected)
        self.assertEqual(result_backtracking[0][0], expected)
    
    

    def test_independence_of_sequence_1(self):
        node_list = [
            ("n0", 0x0, Node6, []),
            ("n1", 0x0, Node3, []),
            ("n2", 0x0, Node4, []),
            ("n3", 0x0, Node5, []),
            ("n4", 0x0, Node5, []),
            ("n5", 0x0, Node5, []),
            ("n6", 0x0, Node4, []),
            ("n7", 0x0, Node6, []), 
            ("n8", 0x0, Node5, [])
        ]
        wire_list = [
            ("w0", "n0", "O1", {("n1", "I1")}),
            ("w1", "n1", "O1", {("n2", "I1")}),
            ("w2", "n1", "O2", {("n3", "I1")}),
            ("w3", "n1", "O3", {("n4", "I1")}),
            ("w4", "n2", "O1", {("n6", "I1")}),
            ("w5", "n6", "O1", {("n5", "I1")}),
            ("w6", "n7", "O1", {("n8", "I1")})
        ]
        topology = Topology(node_list, wire_list)
        w_list = topology.sorted_wires
        perm = itertools.permutations(w_list)
        print(len(list(perm)))
        correct_number_of_solutions = len(topology.parametrized_state_search({}, State_Search_Flags(all_solutions = True, advanced_backtracking = False, visualize=False)))
        for p in itertools.permutations(w_list):
            print(p)
            #topology.sorted_wires = list(map(lambda x: x[0], sorted(list(zip(w_list, list(p))), key= lambda x: x[1])))
            topology.sorted_wires = p
            solutions = topology.parametrized_state_search({}, State_Search_Flags(all_solutions = True, advanced_backtracking =True, print_solutions=False, visualize=False))
            print(len(solutions))
            self.assertEqual(len(solutions), correct_number_of_solutions)

    def test_independence_of_sequence_2(self):        
        enzian = Topology(enzian_nodes, enzian_wires)
        enzian.current_node_state.update({"cpu" : "POWERED_ON", "fpga" : "POWERED_DOWN"})
        expected = len(enzian.parametrized_state_search({}, State_Search_Flags(print_solutions=False, advanced_backtracking=False, extend=False, all_solutions=True)))
        print(expected)
        for i in range(1):
            print(i)
            random.shuffle(enzian.sorted_wires)
            solutions = enzian.parametrized_state_search({}, State_Search_Flags(print_solutions=False, advanced_backtracking=True, extend=False, all_solutions=True))
            self.assertEqual(len(solutions), expected)


class Node1(Node):
    I1 = Input([(4, 9), (25, 60)], "power")
    I2 = Input([{0, 1}], "logical")
    I3 = Input([{6, 3, 4}, {8, 1, 4}], "power")

    def __init__(self, name, bus_addr):
            super(Node1, self).__init__(name, bus_addr, Node1)

class Node2(Node):
    O1 = Output([(0, 25), (0, 250)], [
        Constraint([(5, 5), (44, 44)], {}, partial(Constraint.explicit, "O1", set(), set()))
    ], "power", Wire.gpio_set)
    O2 = Output([{0, 1}], [Constraint([{0, 1}], {},  partial(Constraint.explicit, "O2", set(), set()))], "logical", Wire.gpio_set)
    O3 = Output([{3, 4, 7}, {29, 1, 99}], [Constraint([{3}, {1}], {},  partial(Constraint.explicit, "O3", set(), set()))], "power", Wire.gpio_set)

    def __init__(self, name, bus_addr):
            super(Node2, self).__init__(name, bus_addr, Node2)



    

#required for test parametrized state search
class CPU2(Stateful_Node):
    VDD = Input([(0, 2600)], "power")
    EN1 = Input([{0, 1}], "logical")
    EN2 = Input([{0, 1}], "logical")

    states = (lambda vdd, en1, en2: {
        "POWERED_DOWN" : PowerState({vdd : [(0, 0)], en1 : [{0}], en2 : [{0}]}, {
            "POWERED_ON": [
                ({en1 : [{0}]}, "")
            ], 
            "POWERED_DOWN": []}),
        "POWERED_ON" : PowerState({vdd : [(2300, 2600)], en1 : [{1}], en2 : [{0}]}, {
            "POWERED_DOWN": [
                ({vdd: [(2300, 2400)]}, "wait until " + vdd + " stabilized"),
                ({en1 : [{1}]}, ""),
                ({en2 : [{1}], vdd: [(2000, 2600)]}, "")
            ],
            "POWERED_ON": []})
    }, ["VDD", "EN1", "EN2"])

    def __init__(self, name, bus_addr):
        super(CPU2, self).__init__(name, bus_addr, "POWERED_DOWN", CPU2)



class CPU_3(Stateful_Node):
    VDD33 = Input([(0, 4000)], "power")
    VDD = Input([(0, 2500)], "power")
    EN1 = Input([{0, 1}], "logical") 
    EN2 = Input([{0, 1}], "logical")

    states = (lambda vdd33, vdd, en1, en2: {
        "POWERED_DOWN" : PowerState({vdd33: [(0, 0)], vdd : [(0, 0)], en1 : [{0}], en2 : [{1}]}, {
            "POWERED_ON": [
                ({en1 : [{0}]}, "")
            ], 
            "POWERED_DOWN": []}),
        "POWERED_ON" : PowerState({vdd33: [(3000, 4000)], vdd : [(2000, 2500)], en1 : [{1}], en2 : [{0}]}, {
            "POWERED_DOWN": [
                ({en2 : [{1}]}, ""),
                ({vdd33: [(3000, 4000)], vdd: [(2000, 2500)]}, "wait until " + vdd + " stabilized"), 
                ({en1 : [{1}]}, ""),
                ({vdd: [(2000, 2200)]}, "")

            ],
            "POWERED_ON": []})
    }, ["VDD33", "VDD", "EN1", "EN2"])

    def __init__(self, name, bus_addr):
        super(CPU_3, self).__init__(name, bus_addr, "POWERED_DOWN", CPU_3)




class PowerSupply(Node):
    OUT0 = Output([(0, 12000)], [Constraint([(0, 12000)], {},  partial(Constraint.explicit, "OUT0", set(), set()))], "power", Wire.gpio_set)
    OUT1 = Output([(0, 12000)], [Constraint([(0, 12000)], {},  partial(Constraint.explicit, "OUT1", set(), set()))], "power", Wire.gpio_set)
    OUT2 = Output([(0, 12000)], [Constraint([(0, 12000)], {},  partial(Constraint.explicit, "OUT2", set(), set()))], "power", Wire.gpio_set)

    def __init__(self, name, bus_addr):
        super(PowerSupply, self).__init__(name, bus_addr, PowerSupply)




class Node3(Node):
    device = "node3"
    I1 = Input([{0, 1}], "logical")
    O1 = Output([{0, 1}], [
        Constraint([{1}], {"I1" : [{1}]}, partial(Constraint.explicit, "O1", {"I1"}, set())),
        Constraint([{0}], {"I1" : [{0}]}, partial(Constraint.explicit, "O1", {"I1"}, set()))
    ], "logical", Wire.pin_set)
    O2 = Output([{0, 1}], [
        Constraint([{1}], {"I1" : [{1}]}, partial(Constraint.explicit, "O2", {"I1"}, set())),
       Constraint ([{0}], {"I1" : [{0}]}, partial(Constraint.explicit, "O2", {"I1"}, set()))
    ], "logical", Wire.pin_set)
    O3 = Output([{0, 1}], [
        Constraint([{1}], {"I1" : [{1}]}, partial(Constraint.explicit, "O3", {"I1"}, set())),
        Constraint([{0}], {"I1" : [{0}]}, partial(Constraint.explicit, "O3", {"I1"}, set()))
    ], "logical", Wire.pin_set)

    def __init__(self, name, bus_addr):
        super(Node3, self).__init__(name, bus_addr, Node3)

class Node4(Node):
    device = "node4"
    I1 = Input([{0, 1}], "logical")
    O1 = Output([{0, 1}], [
        Constraint([{0}], {"I1" : [{1}]}, partial(Constraint.explicit, "O1", {"I1"}, set())),
        Constraint([{1}], {"I1" : [{0}]}, partial(Constraint.explicit, "O1", {"I1"}, set())),
    ], "logical", Wire.pin_set)

    def __init__(self, name, bus_addr):
        super(Node4, self).__init__(name, bus_addr, Node4)

class Node5(Node):
    I1 = Input([{0, 1}], "logical")

    def __init__(self, name, bus_addr):
        super(Node5, self).__init__(name, bus_addr,  Node5)

class Node6(Node):
    O1 = Output([{0, 1}], [Constraint([{0}], {}, partial(Constraint.explicit, "O1", set(), set())), Constraint([{1}], {},  partial(Constraint.explicit, "O1", set(), set()))], "logical", Wire.gpio_set)

    def __init__(self, name, bus_addr):
        super(Node6, self).__init__(name, bus_addr, Node6)


        

    
    


if __name__ == '__main__':
    unittest.main()