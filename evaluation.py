#! /usr/bin/env python3

import argparse
import random
import timeit
import copy

from sequence_generation import State_Search_Flags, Topology, topological_sort
from enzian_descriptions import enzian_nodes, enzian_wires, enzian_nodes_EVAL3

problems = [
    ("p1", {"cpu" : "POWERED_ON", "fpga": "POWERED_ON"}, {"vdd_ddrcpu13" : [(1500, 1500)], "vdd_ddrcpu24" : [(1500, 1500)], "vdd_ddrfpga13" : [(1200, 1200)], "vdd_ddrfpga24" : [(1200, 1200)]}, 256),
    ("p2", {"cpu" : "POWERED_ON", "fpga": "POWERED_DOWN"}, {"vdd_ddrcpu13" : [(1500, 1500)], "vdd_ddrcpu24" : [(1500, 1500)]}, 6),
    ("p3", {"cpu" : "POWERED_DOWN", "fpga": "POWERED_DOWN"}, {}, 8),
]

transitions = [
    ("p1", {"cpu" : "POWERED_DOWN", "fpga": "POWERED_DOWN"}, {"cpu" : "POWERED_ON", "fpga": "POWERED_ON"}),
    ("p2", {"cpu" : "POWERED_DOWN", "fpga": "POWERED_DOWN"}, {"cpu" : "POWERED_ON", "fpga": "POWERED_DOWN"}),
    ("p3", {"cpu" : "POWERED_ON", "fpga": "POWERED_DOWN"},  {"cpu" : "POWERED_ON", "fpga": "POWERED_ON"}),
    ("p4", {"cpu" : "POWERED_ON", "fpga": "POWERED_DOWN"}, {"cpu" : "POWERED_DOWN", "fpga": "POWERED_DOWN"}),
    ("p5", {"cpu" : "POWERED_ON", "fpga": "POWERED_ON"}, {"cpu" : "POWERED_ON", "fpga": "POWERED_DOWN"}),
    ("p6", {"cpu" : "POWERED_ON", "fpga": "POWERED_ON"}, {"cpu" : "POWERED_DOWN", "fpga": "POWERED_DOWN"}),        
]


def run_eval1_m1():
    enzian = Topology(enzian_nodes, enzian_wires)

    for (name, node_states, state_dict, number) in problems:
        result_file = open("results/eval1_m1_%s.csv"%name, 'a', buffering=1)
        flags1 = State_Search_Flags(all_solutions= False, advanced_backtracking=False)
        flags2 = State_Search_Flags(all_solutions=False)
        flags3 = State_Search_Flags(use_z3=True)

        for i in range(100):
            print(i)
            enzian.current_node_state = node_states
            random.shuffle(enzian.sorted_wires)
            for w in enzian.wires.values():
                random.shuffle(w.constraints)
            #required since z3 keeps state and since we have permuted every conductor's state possibilities: index of which are hardcoded into the z3 problem instance!
            enzian.generate_z3_solver()
            time1 = timeit.timeit(lambda: enzian.parametrized_state_search({}, flags1, 1), number = 1)
            time2 = timeit.timeit(lambda: enzian.parametrized_state_search({}, flags2, 1), number = 3) / 3
            time3 = timeit.timeit(lambda: enzian.parametrized_state_search({}, flags3, 1), number = 3) / 3
            print(time1)
            print(time2)
            print(time3)
            result_file.write(str(time1) + "," + str(time2) + "," + str(time3) + "\n")

def run_eval1_m2():
    enzian = Topology(enzian_nodes, enzian_wires)

    for (name, node_states, state_dict, number) in problems:
        result_file = open("results/eval1_m2_%s.csv"%name, 'a')
        flags = State_Search_Flags(all_solutions=False)
        for i in range(500):
            print(i)
            enzian.current_node_state = node_states
            random.shuffle(enzian.sorted_wires)
            for w in enzian.wires.values():
                random.shuffle(w.constraints)
            time = timeit.timeit(lambda: enzian.parametrized_state_search({}, flags, 1), number = 3) / 3
            print(time)
            result_file.write(str(time) + "\n")

def run_eval1_m3():
    enzian = Topology(enzian_nodes, enzian_wires)
    for (name, node_states, state_dict, number) in problems:
        result_file = open("results/eval1_m3_%s.csv"%name, 'a')
        flags = State_Search_Flags(all_solutions=True)
        for i in range(500):
            print(i)
            enzian.current_node_state = node_states
            random.shuffle(enzian.sorted_wires)
            for w in enzian.wires.values():
                random.shuffle(w.constraints)
            time = timeit.timeit(lambda: enzian.parametrized_state_search(state_dict, flags, number), number = 3) / 3
            print(time)
            result_file.write(str(time) + "\n")

def run_eval1_m4():
    enzian = Topology(enzian_nodes, enzian_wires)
    for (name, node_states, state_dict, number) in problems:
        result_file = open("results/eval1_m4_%s.csv"%name, 'a')
        flags = State_Search_Flags(all_solutions=False)
        for i in range(500):
            print(i)
            enzian.current_node_state = node_states
            random.shuffle(enzian.sorted_wires)
            for w in enzian.wires.values():
                random.shuffle(w.constraints)
            time1 = timeit.timeit(lambda: enzian.parametrized_state_search({}, flags, 1), number = 3) / 3
            time2 = timeit.timeit(lambda: enzian.parametrized_state_search(state_dict, flags, 1), number = 3) / 3
            print(time1)
            print(time2)
            result_file.write(str(time1) + "," + str(time2) + "\n")


def run_eval2():
    result_file = open("results/eval2.csv", 'a', buffering=1)
    for (problem, initial, end) in transitions:
        time = 0
        #since consumer transitions update the virtual platform state (especially the initial consumer states), we must manually time it thrice
        for i in range(3):
            enzian = Topology(enzian_nodes, enzian_wires)
            enzian.current_node_state = copy.deepcopy(initial)
            time = timeit.timeit(lambda: enzian.stateful_node_update(end, flags = State_Search_Flags(all_solutions=False, visualize=False)), number = 1) + time
            print(initial)
            print(end)
        time = time / 3
        print(time)
        result_file.write(problem + "," + str(time) + "\n")

def run_eval3():
    #Collect data, store sequence to commands.py and G1 to G19 (remove comments to perform)
    #############################################################
    
    enzian = Topology(enzian_nodes_EVAL3, enzian_wires)
    enzian.apply_changes({}, flags= State_Search_Flags(all_solutions = False))
    enzian.commands = enzian.commands + "# code from here:\n"

    # writes event graphs to files G1 to G19:
    enzian.stateful_node_update({"cpu": "POWERED_ON", "fpga": "POWERED_ON"}, flags= State_Search_Flags(all_solutions=True, return_graph=True, prefer_concurrent_interleaving=False))
    enzian.done("results/eval3_sequence.py") #writes command sequence to results/eval3_sequence.py -> must press Enter to continue the evaluation
    ##############################################################


    #Evaluate similarity of order as described in thesis: store results in file "result_eval3.txt":
    ##############################################################
    #G (event graph of manual solution was manually constructed and stored in manual_sequence_event_graph.txt)
    enzian = Topology(enzian_nodes, enzian_wires)
    graph_file = open("manual_sequence_event_graph.txt", 'r')
    graph = eval(graph_file.read())
    graph_file.close()
    #assert that all conductors in G were spelled correctly (since they were manually typed)
    for (c, conductors) in graph.items():
        for w in conductors | {c}:
            name = w
            if w[:4] == "set_":
                name = w[4:]
            if not name in enzian.wires:
                print("%s not in wires" % name)
    #assert that G is acyclic
    print("G is acyclic: %s"% str(not topological_sort(graph) is None))

    result_file = open("results/eval3.txt", 'w')

    #G1 is empty because of the call to apply_changes that put the platform into the appropriate state
    for i in range(1, 20):
        graph_file = open("results/eval3_G%s.txt"%str(i), 'r')
        graph2 = eval(graph_file.read())
        graph_file.close()
        for (c, conductors) in graph.items():
            if c in graph2:
                graph2[c].union(conductors)
            else:
                graph2[c] = conductors
        string = "Union of G%s and G is acyclic : %s" %(str(i), str(not topological_sort(graph2) is None))
        print(string)
        result_file.write(string + "\n")

    result_file.close()

experiments={
    "e1m1"  : run_eval1_m1,
    "e1m2"  : run_eval1_m2,
    "e1m3"  : run_eval1_m3,
    "e1m4"  : run_eval1_m4,
    "e2"    : run_eval2,
    "e3"    : run_eval3
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run evaluation, by default all experiments are run.")
    parser.add_argument("--e1m1", dest="experiments", action="append_const", const="e1m1",
        help="Run measurement 1 of evaluation 1"
    )
    parser.add_argument("--e1m2", dest="experiments", action="append_const", const="e1m2",
        help="Run measurement 2 of evaluation 1"
    )
    parser.add_argument("--e1m3", dest="experiments", action="append_const", const="e1m3",
        help="Run measurement 3 of evaluation 1"
    )
    parser.add_argument("--e1m4", dest="experiments", action="append_const", const="e1m4",
        help="Run measurement 4 of evaluation 1"
    )
    parser.add_argument("--e2", dest="experiments", action="append_const", const="e2",
        help="Run evaluation 2"
    )
    parser.add_argument("--e3", dest="experiments", action="append_const", const="e3",
        help="Run evaluation 2"
    )

    args = parser.parse_args()
    if args.experiments is None:
        es = experiments.keys()
    else:
        es = args.experiments

    for e in es:
        experiments[e]()
