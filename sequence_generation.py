import operator
import functools
import numpy as np
import copy
import sys
import random
import z3
import subprocess
import time
from enum import IntEnum, Enum
#pylint: disable =  E0602

#enums used to make indexing into structures more readable/maintainable
class SET(Enum):
    Explicit = 0
    Implicit = 1


class Possibility(IntEnum):
    State = 0
    Requirements = 1
    Constraints = 2
    Dependency = 3

class WireState(IntEnum):
    State = 0
    Index = 1

class ProposedState(IntEnum):
    State = 0
    Index = 1
    Dependency = 2
    RawReq = 3

#numpy complains if "==" is used directly
def numpy_compare(np_value, tuple_value):
        return all(map(lambda x: operator.eq(*x), zip(np_value, tuple_value)))


#exception used when handling states, generally thrown if the resulting state is empty
class State_Space_Error(Exception):
    def __init__(self, msg):
        self.msg = msg

class Set_Error(Exception):
    def __init__(self, msg):
        self.msg = msg

class z3_Error(Exception):
    def __init__(self, msg):
        self.msg = msg

class Wire_Error(Exception):
    def __init__(self, msg):
        self.msg = msg

def topological_sort(out_going_edges_dict):
    '''topologically sorts the graph described by a dictionary of outgoing edges, returns a list of lists, 
    whereby nodes in the same sublist have the same "rank", i.e. can be permuted arbitrarily'''
    out_going_edges = copy.deepcopy(out_going_edges_dict)
    in_going_edges = {}
    node_list = []
    add_to_outgoing = set()
    for node, neighbours in out_going_edges.items():
        for n in neighbours:
            size = len(neighbours)
            if not n in in_going_edges:
                in_going_edges.update({n: {node}})
            else:
                in_going_edges.update({n: in_going_edges[n] | {node}})
            if not n in out_going_edges:
                add_to_outgoing.add(n)
        out_going_edges[node] = len(neighbours)
        if not node in in_going_edges:
            in_going_edges.update({node: set()})
    for node in add_to_outgoing:
        out_going_edges[node] = 0
    value = True
    while len(out_going_edges) != 0 and value:
        remove_set = set()
        for node, size in out_going_edges.items():
            if size == 0:
                remove_set.add(node)
        if remove_set == set() and len(out_going_edges) != 0:
            value = False
        remove_list = list(remove_set)
        #random.shuffle(remove_list)
        node_list.append(remove_list)
        for node in remove_list:
            #node_list.append(node)
            del out_going_edges[node]
            for n in in_going_edges[node]:
                if n in out_going_edges:
                    out_going_edges.update({n: out_going_edges[n] - 1})
    if not value:     
        return None
    else:
        return node_list


def select_state(state):
    '''selects a single state from a state space of possible states'''
    if is_possibility(state):
        #currently just returns first option...
        return select_state(state[0])
    if isinstance(state, list):
       return list(map(select_state, state))
    if isinstance(state, tuple):
        new_state = (state[0] + state[1]) // 2
        return (new_state, new_state)
    if isinstance(state, set):
        if state == {0, 1}:
            return {0} #try to set enable signals to 0 if possible
        else:
            element = state.pop()
            state = state.add(element)
            return {element}
    else:
        raise State_Space_Error("unknown state format")


#no "splinter" should contain s2
#used to generate z3 constraints
def state_difference(s1, s2):
    if isinstance(s1, list) and isinstance(s2, list):
        return_value = []
        for i in range(len(s2)):
            possibility = state_difference(s1[i], s2[i])
            for state in possibility:
                return_value.append(s1[0:i] + [state] + s1[i+1:])
        return return_value
    if isinstance(s1, set) and isinstance(s2, set):
        s = set.difference(s1, s2)
        if s != set():
            return [set.difference(s1, s2)]
        else:
            return []
    if isinstance(s1, tuple) and isinstance(s2, tuple):
        if s1[1] > s2[1] and s1[0] >= s2[0]:
            return [(s2[1] + 1, s1[1])]
        elif s1[0] < s2[0] and s2[1] >= s1[1]:
            return [(s1[0], s2[0] - 1)]
        elif s1[0] < s2[0] and s2[1] < s1[1]:
            return [(s1[0], s2[0] - 1), (s2[1] + 1, s1[1])]
        else:
            return []

#unites two state dictionaries in place (i.e. d1 will contain united dictionary)
#throws exception if states described by d1 and d2 disagree
def unite_dict(d1, d2):
    '''unites two state dictionaries (state requirements) in place (d1 will contain the united dictionary),
    throws exception if states described by d1 and d2 disagree'''
    for key in d2:
        if key in d1:
            try:
                d1[key] = intersect(d1[key], d2[key])
            except State_Space_Error:
                raise State_Space_Error("requested change of %s to %s does not conform to most general state %s" %(key, d1[key], d2[key]))
        else:
            d1.update({key: d2[key]})

#creates a new dictionary and returns it
def unite_dict_return(d1, d2):
    '''unites two state dictionaries (state requirements) and returns the result in a new dictionary. Throws an exception of d1 and d2 disagree'''
    d3 = copy.deepcopy(d1)
    for key in d2:
        if key in d3:
            try:
                d3[key] = intersect(d3[key], d2[key])
            except State_Space_Error:
                raise State_Space_Error("the dictionaries do not agree on %s; values %s and %s" %(key, d2[key], d3[key]))
        else:
            d3[key] = d2[key]
    return d3


#used by advanced backtracking
def state_union_dict(d1, d2):
    '''unites two state dictionaries (state requirements) in place, but does not throw an exception if their states disagree and instead sets the corresponding conductor state to "None".'''
    for key in d2:
        if key in d1:
            try:
                d1[key] = intersect(d1[key], d2[key]) #can only be sure that intersection won't work
            except State_Space_Error:
                d1[key] = None #will fail "try checks" and will hence be tried
                #raise State_Space_Error("requested change of %s to %s does not conform to most general state %s" %(key, d1[key], d2[key]))
        else:
            d1.update({key: d2[key]})


#computes the union of two states
#not used anymore...
def state_union(space1, space2):
    if type(space1) == list and type(space2)==list and len(space1) == len(space2):
        return list(map(lambda x: intersect(x[0], x[1]), zip(space1, space2)))
    if(type(space1) == tuple and type(space2) == tuple):
        a = min(space1[0], space2[0])
        b = max(space1[1], space2[1])
        if(a > b):
            raise State_Space_Error(
                "resulting space state is empty, invalid wire")
        return((a, b))
    elif (type(space1) == set and type(space2) == set):
        c = set.union(space1, space2)
        if c == set():
            raise State_Space_Error(
                "resulting space state is empty, invalid wire")
        return c
    else:
        #print(str(space1) + " and " + str(space2))
        raise State_Space_Error("incompatible state spaces: " + str(space1) + " and " + str(space2))



def is_possibility(space):
    '''decides if a given state space is a list of cartesian state products or just a single such product.
    
    Would hence return True for [[(0, 2)], [(4, 5)]] or [[(2, 3)]] but False for [(2, 3)]'''
    return isinstance(space, list) and len(space) > 0 and isinstance(space[0], list)

def intersect(space1, space2):
    '''Returns the intersection of two state spaces'''
    if not is_possibility(space1) and not is_possibility(space2):
        return intersect_option(space1, space2)
    if is_possibility(space1) and is_possibility(space2):
        combined_state = []
        for s1 in space1:
            new_state = None
            i = 0
            while new_state is None and i < len(space2):
                try:
                    new_state = intersect_option(space2[i], s1)
                except State_Space_Error:
                    i = i + 1
            if not new_state is None:
                combined_state.append(new_state)
        if len(combined_state) == 0:
            raise State_Space_Error("resulting state is empty")
        else:
            return combined_state
    #elif:
        #return State_Space_Error("%s and %s have an unexpected format" %(str(space1), str(space2)))
    elif is_possibility(space1):
        return intersect_states(space1, [space2])
    else:
        return intersect_states(space2, [space1])

def is_range(state):
    '''determines if a partial state description corresponds to a range of the form (min, max)'''
    return isinstance(state, tuple) and len(state) == 2 and isinstance(state[0], int) and isinstance(state[1], int)


def intersect_option(space1, space2):
    '''intersects two state spaces for which is_possibility returns false, i.e. they correspond to a single cartesian state product'''
    if is_range(space1) and is_range(space2):
        a = max(space1[0], space2[0])
        b = min(space1[1], space2[1])
        if(a > b):
            raise State_Space_Error(
                "resulting space state is empty, invalid wire")
        return (a, b)
    elif isinstance(space1, list) and isinstance(space2, list) and len(space1) == len(space2):
        return list(map(lambda x: intersect_option(x[0], x[1]), zip(space1, space2)))
    elif (type(space1) == set and type(space2) == set):
        c = set.intersection(space1, space2)
        if c == set():
            raise State_Space_Error(
                "resulting space state is empty, invalid wire")
        return c
    else:
        #print(str(space1) + " and " + str(space2))
        raise State_Space_Error("incompatible state spaces: " + str(space1) + " and " + str(space2))


def empty_intersection(name, state_dict1, state_dict2):
    if name[:4] == "set_":
        name = name[4:]
    try:
        intersect(state_dict1[name], state_dict2[name])
    except State_Space_Error:
        return True
    except KeyError:
        return True
    return False

def create_state_possibility(state, most_general_state):
    '''tries to unite the state attribute of an output state possibility with the intersection of amr states given by the conductor's inputs (most_general_state).
    Returns an infeasible state if that is not possible (cannot simply discard the possibilitiy because of other, feasible state updates the possibility might define)'''
    try:
        return intersect(state, most_general_state)
    except State_Space_Error:
        new_state = []
        for elem in most_general_state:
            if isinstance(elem, tuple):
                new_state.append((0, -1))
            elif isinstance(elem, set):
                new_state.append(set())
            else:
                raise State_Space_Error("%s is an unknown state dimension expression" % str(elem))
    return new_state





#used in synthesize_state_updates (updates state of stateful nodes)
#generates all steps (i.e. offsets of entries of reachable) that should be marked reachable (if propagate conditions met)
def generate_all_valid_steps(size):
    '''generates all bit strings of length size.

    Used in synthesize_state_updates to correctly fill in the dp table'''
    if size == 1:
        return [[0], [1]]
    else:
        valid_steps = generate_all_valid_steps(size-1)
        return list(map(lambda x: x + [0], valid_steps)) + list(map(lambda x: x + [1], valid_steps))



#extracts states from states that are possible
def possible(current_state, states):
    '''returns the State Possibilities defined by states for which the state attribute agrees with "current_state"''' 
    possible_states = []
    for state, condition, constraints, dependency in states:
        try:
            s = intersect(state, current_state)
            possible_states.append((s, condition, constraints, dependency))
        except State_Space_Error:
            pass
    return possible_states








class Input(object):
    '''class used to provide Input pin descriptions for consumers and producers'''
    def __init__(self, state_space, wire_type, monitor = None):
        '''generate an input pin description:

        state_space: corresponds to amr

        wire_type: describes the conductor's type, must agree with the Output wire type

        monitor: function of the form (node, conductor_name) -> ((value, current_states) -> (usable, <string of code that returns once conductor adopts value>))

        node corresponds to the component object the input belongs to, and conductor name to the name of the conductor connected to input. 
        Will be passed to monitor when the conductor is instantiated (Wire.__init__)

        usable must evaluate to True or False and indicates if the monitor can be used, according to current states'''
        self.name = None
        self.state_space = state_space
        self.wire_type = wire_type
        self.monitor = monitor


# constraints define conditions on inputs/internal device state that must be observed to ensure the "validity" of this output
class Output(object):
    '''class used to provide output pin descriptions'''
    def __init__(self, state_space, constraints, wire_type, method = None):
        '''generates an output pin description:

        state_space: summarises the state spaces described by the individual state possibilities by the output (as a convex approximation)

        constraints: is a list of Constraint objects, each of which defines a State Possibility.

        wire_type: the type of conductor defined by the output

        method: specifies the set method of the output, used to explicitly update its state. Do not specify if no explicit set possible. Should be of the form:
                (node, pinname) -> (value -> <string of code that updates conductor to value>) 
                Whereby node and pinname correspond to the component object the output belongs to, and pinname to the output pin's name.'''
        self.name = None
        self.state_space = state_space
        self.wire_type = wire_type
        self.constraints = constraints
        if method is None:
            self.set = Output.no_set
        else:
            self.set = method

    @staticmethod
    def no_set(device, pinname):
        return lambda _: Wire.raise_exception("output of wire is not settable, or no set method was specified")

    @staticmethod
    def raise_exception(string):
        raise AttributeError(string)


class Constraint(object):
    '''class used to define a State Possibility'''
    def __init__(self, state_possibility, state_requirements, dependency, complex_constraints = [], dependency_update = None, state_update = None):
        '''defines a State Possibility:

        state_possibility (type state): corresponds to the state attribute

        state requirements (type state dict)

        dependency (type partial function): should correspond to a partial function call  (without node attribute) to Conductor.implicit or Conductor.explicit, defines an Event Graph with implicit or explicit Initiate Event.

        complex_constraints: is a list of of constraints of the following format: (lambda X1, X2, .., Xn: <expression>, [(X1, index1), ..., (Xn, indexn)]), whereby Xi are pinnames of other pins the component defines
        and indexi defines the state dimension that is being constrained.

        dependency_update: specifies how the dependency attribute should be updated, is of the form (next: node -> (() -> index), [dependency0, ..., dependencyn]), 
        whereby node is the component object associated with the Output the Constraint object belongs to, and the index i returned by next specifies that the dependency attribute should be updated with dependencyi.

        state_update: specifies how the state (state_possibility) attribute should be updated, is of the form (node -> (() -> state)), whereby node is the object associated with the Output the constraint belongs to'''

        self.state_possibility = state_possibility
        self.state_requirements = state_requirements
        self.dependency = dependency
        self.complex_constraints = complex_constraints
        self.dependency_update = dependency_update
        self.state_update = state_update


    #flatten the information expressed by a Constraint to a form defined by Possibilty enum
    def create_possibility(self, output_device, most_general_state, name, updates, constraints):
        '''flattens the information expressed by a Constraint to a form defined by Possibility enum (and appends to "constraints"), adds state and dependency updates to the "update" list. Called internally in Conductor initialisation (Wire.__init__)'''
        if not self.state_update is None:
            function = self.state_update(output_device)
            
            #determine current value of state_possibility
            self.state_possibility = function()
            

            #adds a new entry to update, which includes:
            #index of updatable possibility
            #the update function
            #the z3 variable name
            updates.append([len(constraints), Possibility.State, function, "update_%s_%d"%(name, len(constraints))])

        else:
            self.state_possibility = create_state_possibility(self.state_possibility, most_general_state)
            
            
        if not self.dependency_update is None:
            #must retain dependency list defined by dependency_update since they still need to be initialized (by passing "node" to them)!
            (function, dependencies) = self.dependency_update
            function = function(output_device)
            updates.append([len(constraints), Possibility.Dependency, function, dependencies])
            self.dependency = None
        
        constraints.append([self.state_possibility, self.state_requirements, self.complex_constraints, self.dependency])

    def create_bus_constraints(self, output_device, input_set, name, constraints):
        constraints.append([self.state_possibility, self.state_requirements(output_device, input_set), self.complex_constraints, self.dependency(output_device, name, input_set)])

    @staticmethod
    def is_default(node):
        return lambda node=node: 1 if node.is_default else 0

    @staticmethod
    def is_configured(node):
        return lambda node=node: 1 if node.configured else 0


    @staticmethod
    def default_state(node):
        return lambda node=node: node.current





    




    
    @staticmethod
    def explicit(output, before_set, before_complete, node, after_set = set(),  after_complete = set()):
        '''method used to define Event Graphs with an explicit Initiate Event'''
        output_name = getattr(node, output).name
        set_list = [before_set, before_complete, after_set, after_complete]
        set_event = lambda name: "set_" + name
        for i in range(4):
            set_list[i] = set(map(lambda name: getattr(node, name).name, set_list[i]))
            if i >= 2:
                set_list[i] = set(map(set_event, set_list[i]))
        return (SET.Explicit, set_list, lambda _ : {output_name: set()})

    @staticmethod
    def implicit(output, implicit_event, node, before_complete = {}, before_set = {}, after_complete = {}, after_set = {}):
        '''method used to define Event Graphs with an implicit Initiate event'''
        output_name = getattr(node, output).name
        if isinstance(implicit_event, str):
            implicit_event = getattr(node, implicit_event)
        set_list = Constraint.explicit(output, before_set, before_complete, node, after_set, after_complete)[1]
        new_implicit_event = {}
        for name, state in implicit_event.items():
            new_implicit_event[getattr(node, name).name] = state
        return (SET.Implicit, set_list, lambda states, new_implicit_event = new_implicit_event: {output_name : set(filter(lambda x: not empty_intersection(x, new_implicit_event, states), new_implicit_event.keys()))})

        

    
    
    @staticmethod
    def indep(output, node):
        output_name = getattr(node, output).name
        return {output_name: {"set_" + output_name}}

    @staticmethod
    def off_because(output, reason, node):
        output_name = getattr(node, output).name
        reason_name = getattr(node, reason).name
        return {output_name: {reason_name}}

    @staticmethod
    def settable(output, supplies, enable, node):
        output_name = getattr(node, output).name
        supplies_set = {getattr(node, supply).name for supply in supplies}
        if enable is None:
            return {"set_" + output_name: supplies_set, output_name : {"set_" + output_name} | supplies_set}
        else:
            enable_name = getattr(node, enable).name
        
            #return {"set_" + output_name: supplies_set, "set_" + enable_name: {"set_" + output_name} , output_name : {enable_name}}
            return {"set_" + output_name: supplies_set, "set_" + enable_name: {"set_" + output_name} | supplies_set , output_name : {enable_name, "set_" + output_name} | supplies_set}
    
    @staticmethod
    def enable(enable, supplies, node):
        enable_name = getattr(node, enable).name
        supplies_set = {getattr(node, supply).name for supply in supplies}
        return {"set_" + enable_name: supplies_set, enable_name: {"set_" + enable_name} | supplies_set}
        #return {"set_" + enable_name: supplies_set, enable_name: {"set_" + enable_name}}

    @staticmethod
    def on(output, supplies, enable, node):
        output_name = getattr(node, output).name
        supplies_set = {getattr(node, supply).name for supply in supplies}
        if enable is None:
            return {output_name: supplies_set}
        else:
            enable_name = getattr(node, enable).name
            return {output_name: supplies_set | {enable_name}}

    @staticmethod
    def isl_on(output, setters, enable, supplies, node):
        enable_name = getattr(node, enable).name
        setter_set = {getattr(node, setter).name for setter in setters}
        output_name = getattr(node, output).name
        supplies_set = {getattr(node, supply).name for supply in supplies}
        return {
            output_name: supplies_set | {enable_name} | setter_set, 
            "set_" + enable_name : setter_set
        }

    
        




# replaces statically defined input and output in devices it connects with a wire object => original input/output definition
# in class becomes inaccessible => make sure that all relevant information about input and outputs are copied to wire object
class Wire(object):
    '''class used to internally construct Conductors given Component and Platform descriptions.'''

    def __init__(self, name, output_device, output_name, input_set):
        '''constructs a Conductor:
        
        name (String): specifies the conductor's name,
        
        output device (Node instance): refers to the producer instance (Node object) which defines the output pin the conductor is connected to

        output_name (String): specifies the name of the output pin the conductor is connected to

        input_set (Set of (Node instance, String)): specifies the set of inputs the conductor is connected to, as tuples of (Node instance, String), whereby the former references the component instance that defines the input, 
        and the latter indicates the name of the input pin.'''


        _output = getattr(output_device, output_name)
        if not isinstance(_output, Output):
            print("\ngiven output of wire " +
                  name + " has already been assigned!\n")
            raise AttributeError(self)
        self.pin_name = output_name
        self.type = _output.wire_type
        self.constraints = []
        self.input_set = input_set
        self.output_device = output_device
        self.name = name
        self.most_general_state = _output.state_space
        self.monitors = []

        monitors = set()

        #check types, unify output/input constraints, modify input attributes to point to wire
        for input_node, input_name in input_set:
            _input = getattr(input_node, input_name)
            if input_node is output_device:
                print("Warning: output of device " +
                  input_node.name + " connected to own input")
            if not (isinstance(_input, Input)):
                print("\ngiven input or output of wire " +
                  name + " has already been assigned!\n")
                raise AttributeError(self)
            if not (_input.wire_type == _output.wire_type):
                if _input.wire_type == "monitor":
                    monitors.add((input_node, input_name))
                else:
                    print("\ninput and output given to wire " +
                    name + " require different wire types!\n")
                    raise AttributeError(self)
            if not _input.monitor is None:
                self.monitors.append(_input.monitor(input_node, name))
            self.most_general_state = intersect(self.most_general_state, _input.state_space)
            if not (input_node, input_name) in monitors:
                setattr(input_node, input_name, self)
        
        #remove purely monitoring - based connections
        input_set.difference_update(monitors)

        self.updates = []
        for constraint in _output.constraints:
            if self.type == "bus":
                constraint.create_bus_constraints(output_device, input_set, name, self.constraints)
            else:
                constraint.create_possibility(output_device, self.most_general_state, name, self.updates, self.constraints)
        

        #instantiate wire set method
        self.set = _output.set(output_device, output_name)

        #let output attribute point to wire
        setattr(output_device, output_name, self)

    def update(self, topology):
        '''updates the conductor's State Possibilities according to the dependency and state update they define.
        the parameter topology is the entire Topology (Platform) object and is required to adequately update the z3 variables.'''

        for index, update_type, function, arg in self.updates:
            if update_type == Possibility.Dependency:
                self.constraints[index][Possibility.Dependency] = arg[function()]
            elif update_type == Possibility.State:
                value = function()
                self.constraints[index][Possibility.State] = value
                topology.updatable_vars[arg] = topology.format_state(value)
            else:
                raise Wire_Error("update %i (%s) has an unexpected format" %(i, self.updates[i]))
               

    


    #collection of different set methods used by components:

    @staticmethod
    def vid_set(node, pinname):
        if pinname == "B_FDV_1V8":
            offset = 8
        if pinname == "B_CDV_1V8":
            offset = 0

        # XXX: The new API models this as a device with voltage controls so we need to reverse some stuff
        # here.
        def offset_to_control(offset):
            if offset == 0:
                return "CDV_1V8"
            elif offset == 8:
                return "FDV_1V8"
            else:
                return "INVALID_CONTROL"

        def binary_to_voltage(binary):
            voltage = 1.6125 - (binary * 0.00625)
            if voltage < 0.5:
                voltage = 0
            elif voltage > 1.6:
                voltage = 0
            return voltage

        def fun(value, offset=offset):
            commands = node.configure()
            commands.append("power.set_device_control('isl6334d_ddr_v', '%s', %.3f)" % (
                offset_to_control(offset),
                binary_to_voltage(int("".join(str(*x) for x in value), 2))
            ))
            return "\n".join(commands)
        return fun


    @staticmethod
    def cpu_clk_ok(node, pinname):
        pins = ["B_CLOCK_BLOL", "B_CLOCK_CLOL"]
        wait_for_string = "\n".join(map(lambda pin: "wait_for('%s', lambda: gpio.get_value('%s'), True, 10)" % (pin, pin), pins))
        set_string = lambda s: "gpio.set_value('C_PLL_DCOK', %s)" % s
        return lambda value: wait_for_string + "\n" + set_string(True) if value == [{1}] else set_string(False)

    @staticmethod
    def fpga_clk_ok(node, pinname):
        return lambda value, pinname = pinname: "" if value == [{0}] else "wait_for('%s', lambda: gpio.get_value('%s'), True, 1)" % (pinname, pinname)
        

    @staticmethod
    def gpio_set(node, pinname):
        def fun(value, pinname=pinname):
            bool_value = bool(list(value[0])[0])
            # XXX: PSUP_ON is special as we need to initialize the fan controller that we don't model yet
            # and also enable/disable alerts
            if pinname == "B_PSUP_ON":
                if bool_value:
                    commands = [
                        "fault.mask_scram()",
                        "power.disable_bus_alerts('pwr_fan')",
                        "gpio.set_value('%s', %s)" % (pinname, bool_value),
                        "init_fan_control()",
                        "fault.unmask_scram()",
                        "power.enable_bus_alerts('pwr_fan')"
                    ]
                else:
                    commands = [
                        "fault.mask_scram()",
                        "power.disable_bus_alerts('pwr_fan')",
                        "gpio.set_value('%s', %s)" % (pinname, bool_value)
                        # XXX: We would also need to deinit devices but this is enough for now
                    ]
            else:
                commands = [
                    "gpio.set_value('%s', %s)" % (pinname, bool_value)
                ]
            return "\n".join(commands)
        return fun
    
    @staticmethod
    def pin_set(node, pinname):
        def fun(value, device=node.device, pinname=pinname):
            commands = node.configure()
            commands.append("power.set_device_control('%s', '%s', %s)" % (
                str(device),
                pinname,
                'True' if value == [{1}] else 'False'
            ))
            return "\n".join(commands)
        return fun
    
    @staticmethod
    def voltage_set(node, pinname):
        def fun(value, device=node.device):
            commands = node.configure()
            commands.append("power.device_write('%s', 'VOUT_COMMAND', %s)" % (
                str(device), str(value[0][0] / 1000)
            ))
            return "\n".join(commands)
        return fun
    
    @staticmethod
    def ir_set(node, pinname):
        loop = node.loop1
        if len(pinname.split('_')) > 1:
            loop = node.loop2
        
        def fun(value, node=node, loop=loop):
            commands = node.configure()
            commands.append("power.device_write('%s', 'VOUT_COMMAND', %s)" % (
                loop,
                str(value[0][0] / 1000)
            ))
            return "\n".join(commands)
        return fun

    @staticmethod
    def no_set(node, pinname):
        return lambda _: Wire.raise_exception("output of wire is not settable, or no set method was specified")

    @staticmethod
    def raise_exception(string):
        raise Set_Error(string)

    @staticmethod
    def clock_config(node, pinname):
        def fun(_):
            return "\n".join(node.configure())
        return fun



class Node(object):
    '''base class used to describe a component, every component description must inherit from Node'''
    def __init__(self, name, bus_addr, node_class):
        self.name = name
        self.bus_addr = bus_addr
        self.subclass = node_class


    def update(self, states):
        '''generic update method, can be overwritten by subclasses'''
        pass
        

    def get_labels(self):
        '''retrieves the labelling of the node used to graphically represent it'''
        input_string = None
        output_string = None
        attributes = set(self.subclass.__dict__) | set(self.__dict__)
        for attr in attributes:
            #only draw connected ports
            if attr in self.__dict__:
                obj = self.__dict__[attr]
                if isinstance(obj, Wire):
                    if obj.output_device.name == self.name:
                        if output_string is None:
                            output_string = "<%s> %s" %(attr, attr)
                        else:
                            output_string += " | <%s> %s" %(attr, attr)
                    else:
                        if input_string is None:
                            input_string = "<%s> %s" %(attr, attr)
                        else:
                            input_string += " | <%s> %s" %(attr, attr)
        strings = [input_string, output_string]
        additions = [("{", "{{", "} | "), ("}", " | {", "}}")]
        for i in range(len(strings)):
            empty, left, right = additions[i]
            if strings[i] is None:
                strings[i] = empty
            else:
                strings[i] = left + strings[i] + right
        return strings[0] + self.name + strings[1]

        



class PowerState(object):
    '''class used to represent a consumer's power state'''
    def __init__(self, most_general_state, state_change_sequence):
        '''constructs a power state representation of a consumer:

        most_general_state (state dict): describes the general consumer demands associated with the power state

        state_change_sequence (dictionary PowerState -> transition sequence): a dictionary entry P: trans specifies that transition sequence trans must be performed to change from power state P to the power state described by this PowerState instance.
        Trans is assumed to be in an incremental form.'''
        self.most_general_state = most_general_state
        self.state_change_sequence = state_change_sequence



#defines initialisation methods and transition getters
class Stateful_Node(Node):
    '''Class used to describe consumers, inherits from the general component class Node'''
    def __init__(self, name, bus_addr, default_state, subclass):
        self.subclass = subclass
        self.default_state = default_state
        self.states = None
        super(Stateful_Node, self).__init__(name, bus_addr, subclass)

    def get_transition(self, current_state, new_state):
        '''returns the sequence of consumer demands that implements the transition for current_state to new_state'''
        return self.states[new_state].state_change_sequence[current_state]
    
    def get_most_general_states(self, current_state):
        '''return the consumer demands associated with the power state "current_state"'''
        return self.states[current_state].most_general_state

    def print_transitions(self):
        '''debugging print function that prints all transitions the consumer defines'''
        for name, state in self.states.items():
            print(name)
            for init_state, sequence in state.state_change_sequence.items():
                print(init_state)
                print(sequence)

    def extend_states(self):
        '''constructs absolute consumer demands of transitions from incremental transition descriptions'''
        for end_state in self.states:
            for init_state, sequence in self.states[end_state].state_change_sequence.items():
                last = self.get_most_general_states(init_state)
                for i in range(len(sequence)):
                    last = copy.deepcopy(last)
                    last.update(sequence[i][0])
                    sequence[i] = (last, sequence[i][1])
                last.update(self.get_most_general_states(end_state))
                sequence.append((last, "")) #makes transition's end state consistent with final node state
    
    def init_states(self):
        '''renames local pin names of PowerState descriptions to feature conductor names and constructs absolute transitions'''
        fun, args = self.subclass.states
        args = map(lambda x: getattr(self, x).name, args)
        self.states = fun(*args)
        self.extend_states()






#object that collects all the flags and objects passed to the state_search 
class State_Search_Flags(object):
    '''object specifying the set of State_Search_Flags that can be passed to various methods to change their behaviour'''
    def __init__(
        self,
        all_solutions = True,
        extend = True,
        ignore_nodes = set(),
        record_unchanged = False,
        print_solutions = False,
        no_output = False,
        advanced_backtracking = True,
        use_z3 = False,
        print_changed_req = True,
        visualize = False,
        return_graph = False,
        prefer_concurrent_interleaving = True    
    ):
        self.aggressive = not all_solutions
        self.advanced_backtracking = advanced_backtracking
        self.all_solutions = all_solutions
        self.extend = extend
        self.ignore_nodes = ignore_nodes
        self.record_unchanged = record_unchanged
        self.print_solutions = print_solutions
        self.no_output = no_output
        self.use_z3 = use_z3
        self.print_changed_req = print_changed_req
        self.visualize = visualize and global_visualise
        self.return_graph = return_graph
        self.prefer_concurrent_interleaving = prefer_concurrent_interleaving


#used in shared_wire_states array because numpy does not support arrays of dictionaries... :|
class Dictionary_object(object):
    '''ugly helper class since numpy does not support arrays of dictionaries'''
    def __init__(self, wire_list):
        self.w = {}
        for wire in wire_list:
            self.w[wire] = None



class Topology(object):
    '''class used to construct platform instances'''
    def __init__(self, nodes, wires, rank_length = 1, speed = 0.5, sorted_wires = None):
        '''constructs a reduced platfrom instance from component and connection descriptions:

        nodes: a list of component descriptions of the following from (component_name, bus_address, component_class, <list of additional attributes>)
        whereby the component_class specifies the class of which the described component is an instance (said class must inherit from Node for a producer / Stateful_Node for a consumer)

        wires: a list of connection descriptions of the following format: (conductor name, name of output component, name of output pin, Set of: (name of input component, name of input pin))'''

        self.commands = ""
        self.nodes = {}
        self.wires = {}
        self.stateful_nodes = set()
        self.most_general_state = {}
        self.current_wire_state_range = {}
        self.current_wire_state = {}
        self.current_node_state = {}
        self.speed = speed
        
        #attributes storing z3 expression of problem
        self.problem = z3.Solver()
        self.vars = {}
        #stores variables corresponding to updatable state_possibilities
        self.updatable_vars = {}
        
        #used to construct dependency graph of wires
        out_going_wires = {}
        incoming_wires = {}
        graph = {}

        #define nodes
        for name, bus_addr, class_obj, args in nodes:
            out_going_wires[name] = set()
            incoming_wires[name] = set()

            #instantiate node object
            new_node = class_obj(name, bus_addr, *args)
            self.nodes.update({name: new_node})

            if isinstance(new_node, Stateful_Node):
                self.stateful_nodes.add(name)
            
        graph_w = {}
        #define wires (requires nodes to be defined already)
        for name, output_device, output_name, input_set in wires:
            graph[name] = set()
            out_going_wires[output_device].add(name)
            input_nodes_set = set()

            
            for (input_node, input_name) in input_set:
                incoming_wires[input_node].add(name)
                input_nodes_set.add((self.nodes[input_node], input_name))


            w = Wire(name, self.nodes[output_device], output_name, input_nodes_set)
            input_set = set(map(lambda x : (x[0].name, x[1]), input_nodes_set))
            graph_w[name] = [output_device, output_name, input_set, w.type]
            self.wires.update({name: w})
            self.most_general_state.update({name: self.wires[name].most_general_state})
            self.generate_vars(w)
            

        
        #rename state possibilities to feature conductor names instead of local pin names
        #Initialise dependencies
        for wire in self.wires.values():
            new_constraints = []
            out = wire.output_device
            if not wire.type == "bus":
                for i in range(len(wire.updates)):
                    #generate dependency possibilities in constraints that feature dependecy updates
                    index, update_type, function, argument = wire.updates[i]
                    if update_type == Possibility.Dependency:
                        wire.constraints[index][update_type] = argument[function()]
                        wire.updates[i][3] = list(map(lambda dep: dep(out), argument))
                for state, condition, constraint, dependency in wire.constraints:
                    new_condition = {getattr(out, n).name : state for n, state in condition.items()}
                    new_constraint = []
                    for fun, variables in constraint:
                        new_vars = []
                        for name, index in variables:
                            new_vars.append((getattr(out, name).name, index))
                        new_constraint.append((fun, new_vars))
                    #generate local dependency graph
                    new_dependency = dependency(out)
                    new_constraints.append([state, new_condition, new_constraint, new_dependency])
                wire.constraints = new_constraints
            
        #generate a z3 solver instance based on self.vars and the conductor descriptions:
        self.generate_z3_solver()


        graph_nodes = {}
        #construct dependency graph of wires
        for node in self.nodes:
            if node in self.stateful_nodes:
                attr = {"fontsize" : 25}
            else:
                attr = {"fontsize" : 20}
            graph_nodes[node] = (self.nodes[node].get_labels(), attr)
            for out in out_going_wires[node]:
                for inp in incoming_wires[node]:
                    graph[inp].add(out)
        if sorted_wires is None:
            self.sorted_wires = list(self.wires.keys()) #topological_sort(graph)
        else:
            self.sorted_wires = sorted_wires#list(self.wires.keys())

        #object that handles visualisation of updates
        # self.system = System(graph_nodes, graph_w)


        

        #initialise stateful nodes (requires wires to be instantiated already)
        for name in self.stateful_nodes:
            self.nodes[name].init_states()
            self.current_node_state[name] = self.nodes[name].default_state

    
    def done(self, path):
        '''used to ensure that process stays alive until user has terminated interaction with visualisation
    by pressing ESCAPE'''
        commands = open(path, 'w')
        commands.write(self.commands)
        commands.close()
    
    #methods used to express constraints in z3
    #---------------------------------------------------------------------------------------------------
    def generate_z3_solver(self):
        self.problem = z3.Solver()
        for wire in self.wires.values():
            self.problem.add(self.generate_constraints(wire))
        #add current updatable constraints to problem:
        self.problem.push()
        self.problem.add(self.translate_state_dict(self.updatable_vars))

    
    
    def generate_vars(self, wire):
        '''generates z3 variables, based on the conductor (Wire) instance "wire" that is passed to it'''
        names = self.get_names(wire.name)
        state_length = self.get_state_length(wire.most_general_state)
        #updatable_variables
        for (index, update_type, _, varname) in wire.updates:
            if update_type == Possibility.State:
                names.extend(self.get_names(varname, state_length))
                #initial state
                self.updatable_vars[varname] = self.format_state(wire.constraints[index][0])
        if wire.type == "logical":
            for n in names:
                self.vars[n] = z3.Bool(n)
        else:
            for n in names:
                self.vars[n] = z3.Int(n) #replace with int, see what works better?
        #variable for the chosen state_possibility
        self.vars[wire.name + "_"] = z3.Int(wire.name + "_")

    @staticmethod
    def to_Bool(integer, var):
        '''translates logical states to appropriate z3 boolean literals:

        integer (type int): must be 0 or 1

        var: the Z3 Boolean variable for which the literal should be constructed
        '''
        if integer == 1:
            return var
        else:
            return z3.Not(var)

    def translate_state(self, state, names, variables = None):
        '''translates a state space to an appropriate z3 constraint:

        state: the state space that should be translated,

        names: (list of strings) the name of the z3 variables assigned to each state dimension of state

        variables: (dictionary mapping names to z3 variables): the variables that should be used to resolve variable names (used when resolving complex constraints)'''

        if variables is None:
            variables = self.vars
        if not is_possibility(state):
            state = [state]
        option_list = []
        for state_option in state:
            state_list = list(zip(state_option, names))
            fun_list = []
            for state, name in state_list:
                var = variables[name]
                if isinstance(state, tuple):
                    if isinstance(state[0], str) and isinstance(state[1], str):
                        try:
                            fun_list.append(lambda state= variables[state[0]], var = var: state <= var)
                            fun_list.append(lambda state= variables[state[1]], var = var: var <= state)
                        except KeyError:
                            raise z3_Error("either of %s and %s is an unknown z3 variable name" %(state[0], state[1]))
                    else:
                        fun_list.append(lambda state=state, var=var: state[0] <= var)
                        fun_list.append(lambda state=state, var=var: var <= state[1])
                if isinstance(state, set):
                    if z3.is_bool(var):
                        if len(state) > 1:
                            fun_list.append(lambda state=state, var=var: z3.Or(*list(map(lambda x: self.to_Bool(x, var) , state))))
                        else:
                            #why is there no get method for sets in python... why??
                            s = state.pop()
                            state.add(s)
                            fun_list.append(lambda var=var, state=s: self.to_Bool(state, var))
                    else:
                        fun_list.append(lambda var=var, state=state: z3.Or(*list(map(lambda s:var == s, state))))
                if isinstance(state, str):
                    try:
                        fun_list.append(lambda var = var, state = variables[state]: var == state)
                    except KeyError:
                        raise z3_Error("%s is an unknown z3 variable name" %(state))
                


            option_list.append(z3.And(*list(map(lambda x: x(), fun_list))))
        return(z3.Or(*option_list))


    def translate_state_dict(self, state_dict):
        '''translates a state dictionary (state requirement) to an appropriate z3 constraint'''
        constraints = []
        for name, state in state_dict.items():
            names = self.get_names(name, len(state))
            constraints.append(self.translate_state(state, names))
        return z3.And(*constraints)

    #returns variables names to represent all state dimensions of a given wire or a given name and length
    def get_names(self, name, length = None):
        '''returns variables names to represent all state dimensions of a given conductor or a given name and length:

        name (string): either specifies a platform conductor (then length must agree with the number of state spaces said conductor features or can be None) or any string
        length (int): may only be None if name corresponds to the name of a platform conductor'''

        if length is None:
            length = len(self.most_general_state[name])
        elif name in self.most_general_state and length != len(self.most_general_state[name]):
            raise z3_Error("given length %d of wire %s does not agree with the length %d of its most general state" %(length, name, len(self.most_general_state[name])))
        return list(map(lambda x, name=name: name + "_" + str(x), list(range(length))))

    
    def get_state_length(self, state):
        '''returns the number of variables necessary to represent the state space "state", used to integrate state updates defined by State Possibilities into z3'''
        if is_possibility(state):
            state = state[0]
        return functools.reduce(lambda x, y: x + 2 if isinstance(y, tuple) else x + 1, state, 0)

    def format_names(self, names, state):
        '''formats names according to state: returns an object of the same format as state, but with each state dimension replaced with the variables needed to represent it'''
        if is_possibility(state):
            state = state[0]
        if self.get_state_length(state) != len(names):
            raise z3_Error("state %s cannot be represented by names %s" %(str(state), str(names)))
        formatted_names = []
        for elem in state:
            if isinstance(elem, set):
                formatted_names.append(names.pop(0))
            elif isinstance(elem, tuple) and len(elem) == 2:
                name1 = names.pop(0)
                name2 = names.pop(0)
                formatted_names.append((name1, name2))
            else:
                raise z3_Error("%s in state %s has an unknown format" %(str(elem), str(state)))
        return formatted_names

    def format_state(self, state):
        '''flattens "state" to a list, such that said list features an entry for every variable required to represent "state", and said entry corresponds to the set of values the variable may attain'''
        new_states = []
        for elem in state:
            if isinstance(elem, tuple) and len(elem) == 2:
                new_states.extend(list(map(lambda x: {x}, elem)))
            elif isinstance(elem, set):
                new_states.append(elem)
            else:
                raise z3_Error("%s in state %s has an unknown format" %(str(elem), str(state)))
        return new_states
        

    def get_complex_constraint(self, constraints):
        '''translates a complex constraint to a z3 constraint'''
        c = []
        for fun, variables in constraints:
            constrained_vars = []
            for name, index in variables:
                var_name = self.get_names(name)[index]
                constrained_vars.append(self.vars[var_name])
            c.append(lambda fun=fun, constrained_vars = constrained_vars:fun(*constrained_vars))
        return z3.And(*list(map(lambda x:x(), c)))
            


    def generate_constraints(self, wire):
        '''translates the conductor referenced by the Wire instance "wire" to appropriate z3 constraints'''
        possibilities = []
        for i in range(len(wire.constraints)):
            state, conditions, complex_constraints, _ = wire.constraints[i]
            update = list(filter(lambda x: x[0] == i and x[1] == Possibility.State, wire.updates))
            if len(update) > 1:
                raise State_Space_Error("update index %d of wire %s present multiple times: %s" %(i, wire.name, update))
            if len(update) > 0:
                state_length = self.get_state_length(state)
                state = self.format_names(self.get_names(update[0][3], state_length), state)
            new_condition = copy.deepcopy(conditions)
            new_condition[wire.name] = state
            new_condition = self.translate_state_dict(new_condition)
            possibilities.append(z3.And(new_condition, self.get_complex_constraint(complex_constraints), self.vars[wire.name + "_"] == i))
        return z3.Or(*possibilities)


    def recover_solution(self, model):
        '''formats a model returned by the z3 solver to a state assignment -> glues the different dimensions back together'''
        state = copy.deepcopy(self.most_general_state)
        possibility = {}
        for d in model.decls():
            name = str(copy.deepcopy(d.name()))
            value = model[d]
            if name[:7] == "update_":
                pass #ignore updatable constraints
            elif name[-1] == "_":
                possibility[name[:-1]] = value.as_long()
            else:
                index = int(name[-1])
                name = name[:-2]
                if z3.is_true(value):
                    value = {1}
                elif z3.is_false(value):
                    value = {0}
                elif isinstance(state[name][index], tuple):
                    value = (value.as_long(), value.as_long())
                else:
                    value = set([value.as_long()])
                state[name][index] = value
        for name, index in possibility.items():
            state[name] = (state[name], None, self.wires[name].constraints[index][Possibility.Dependency], self.wires[name].constraints[index][Possibility.Requirements])
        return state
        
    #-----------------------------------------------------------------------------------------------------

    #can be passed to "sorted" as key
    def wire_sort_function(self, wire):
        return self.sorted_wires.index(wire)
    
    #constructs a dictionary containing all wires states required by the stateful nodes not in the "ignore_node" set
    def get_stateful_node_dict(self, ignore_node):
        '''constructs a state dictionary that combines all conductor states required by the current power states of the consumers not in the "ignore_node" set'''
        states = self.current_node_state
        stateful_dict = {}
        for node in self.stateful_nodes:
            if not node in ignore_node:
                required_states = self.nodes[node].get_most_general_states(states[node])
                for wire in required_states:
                    if wire in stateful_dict:
                        try:
                            stateful_dict[wire] = intersect(required_states[wire], stateful_dict[wire])
                        except State_Space_Error:
                            raise State_Space_Error("requested changes do not conform to current state of stateful node %s" % node)
                    else:
                        stateful_dict.update({wire: required_states[wire]})
        return stateful_dict


    #extend dictionary passed to synthesize_wire_updates with required wire states of current node states
    def extend_to_stateful_nodes(self, wire_state_dict, ignore_node):
        '''extends state dictionary (consumer demands) to include the demands associated with the current consumer power states:
        
        wire_state_dict: the state dictionary containing current specific consumer demands
        
        ignore_nodes: set of consumer names whose current power states should be ignored (used if method called in context of a power state transition)'''
        stateful_dict = self.get_stateful_node_dict(ignore_node)
        new_wire_state_dict = copy.deepcopy(wire_state_dict)
        for wire in stateful_dict:
                if wire in new_wire_state_dict:
                    try:
                        new_wire_state_dict[wire] = intersect(stateful_dict[wire], new_wire_state_dict[wire])
                    except State_Space_Error:
                        raise State_Space_Error("requested change %s to %s does not conform to current state of stateful nodes" %(wire, wire_state_dict[wire]))
                else:
                    new_wire_state_dict.update({wire: stateful_dict[wire]})
        return new_wire_state_dict
            

    
    def state_update(self, wire_state_range, wire_state):

        '''update the virtual state of the topology according to the arguments passed to it:

        wire_state_range: dictionary containing the entire state space mapping returned by the update generation procedure

        wire_state: dictionary containing the chosen state assignment'''

        #update component and conductor states according to new virtual state (used for state/dependency updates)
        for node in self.nodes.values():
            node.update(wire_state)
        for wire in self.wires.values():
            wire.update(self) #pass topology s.t. updatable z3 vars can be adjusted

        #adjust z3 problem to feature new constraints introduced by state updates in state possibilities:
        self.problem.pop()
        self.problem.push()
        self.problem.add(self.translate_state_dict(self.updatable_vars))


        for name, state in wire_state_range.items():
            if name in self.wires:
                try:
                    unified_state = intersect(state, self.wires[name].most_general_state)
                    if state != unified_state:
                        raise State_Space_Error("")
                    self.current_wire_state_range[name] = state
                except State_Space_Error:
                    raise State_Space_Error(
                        "given state %s for %s does not conform to state space of wire" % (state, name))
            else:
                print("no wire in topology with name " + name)
                raise AttributeError
        for name, state in wire_state.items():
            if name in self.current_wire_state_range:
                try:
                    unified_state = intersect(state, self.current_wire_state_range[name])
                    if state != unified_state:
                        raise State_Space_Error("")
                    self.current_wire_state[name] = state
                except State_Space_Error:
                    raise State_Space_Error("given state %s for %s does not agree with current wire range %s" % (state, name, self.current_wire_state_range[name]))
            elif not name in self.wires:
                print("no wire in topology with name " + name)
                raise AttributeError


    #methodes used by stateful nodes updates (for consumer power state transitions)
    #---------------------------------------------------------------------------------------------
   
    def check_feasibility(self, index, dp_table):
        '''uses the z3 solver to check if entry of the dp_table specified by index is feasible:
        
        index: tuple of indices of length dim(dp tapble), specifies an entry of the dp table'''
        constraints = {}
        for j in range(len(index)):
            try:
                #try to unite the consumer demand dictionaries of all consumer dimensions
                unite_dict(constraints, dp_table[j][index[j]][0])
            except State_Space_Error:
                return False
        self.problem.push()
        self.problem.add(self.translate_state_dict(constraints))
        success = self.problem.check() == z3.sat
        self.problem.pop()
        return success


    #uses z3 solver to determine feasible interleavings (using dynamic programming)
    def determine_reachable(self, dp_table, prefer_concurrent):
        '''uses the z3 solver to construct a reachable table that marks if a dp-table entry is reachable and if yes, from which other entry it could be reached'''
        dimensions = tuple(map(len, dp_table))
        t = [(str(i), "int32") for i in range(len(dimensions))]
        size = functools.reduce(lambda x, y: x * y, dimensions)
        fill_value = tuple([-1 for i in range(len(dimensions))]) #tuple filled with -1 if length #nodes
        all_zeros = [0 for i in range(len(dimensions))]
        reachable = np.ndarray(dimensions, dtype=t, buffer = np.array([fill_value for i in range(size)]))
        feasible = np.zeros(dimensions)
        steps = generate_all_valid_steps(len(dimensions))
        steps.remove(all_zeros)
        for i in np.ndindex(dimensions):
            #reachable entry only propagates "reachable" if its index is (0, 0, ..., 0)
            #or if it is feasible and was reached before
            if (sum(i) == 0 or not numpy_compare(reachable[i], fill_value)) and self.check_feasibility(i, dp_table):
                feasible[i] = 1
                for step in steps:
                    #reachable propagated to all entries that are "one step away" (also diagonally over several dimensions)
                    index = tuple(map(lambda x: x[0] + x[1], zip(step, i)))
                    try:
                        #REGULAR REACHABLE CONSTRUCTION:
                        if prefer_concurrent:
                            if numpy_compare(reachable[index], fill_value):
                                reachable[index] = i
                        else:
                            #CONSTRUCTION FOR EVAL 3:
                            reachable[index] = i
                    except:
                        pass
        if numpy_compare(reachable[fill_value], fill_value): #if last element was not reached
            raise Synthesis_Error("no feasible solution")
        print(reachable)
        return reachable, dimensions

    #extracts interleaving found by dynamic programming (determine_reachable)
    def extract_solution(self, reachable, dimensions):
        '''extracts a path through the dp table from the reachable table constructed by determine_reachable'''
        sequence = []
        current = tuple(map(lambda x: x-1, dimensions)) #last index
        fill_value = tuple([-1 for i in range(len(dimensions))])
        while not current == fill_value:
            sequence.append(current)
            #numpy complains about tuple(reachable[current])...
            current = tuple(reachable[current][i] for i in range(len(dimensions)))
        list.reverse(sequence)
        return sequence


    #given feasible path through reachable array (as provided by "sequence"), constructs wire_state_dicts for transitions
    #and collects remarks
    def construct_interleavings(self, sequence, dp_table, node_list):
        '''construct a valid interleaving from a feasible path through the dp table given by sequence'''
        interleavings = []
        current_constraints = {node : {} for node in node_list}
        current_index = tuple(-1 for i in range(len(node_list)))
        for next_index in sequence:
            remark = ""
            drawing_label = ""
            for i in range(len(node_list)):
                node = node_list[i]
                if current_index[i] != next_index[i]:
                    drawing_label += " %s: transition %d," %(node_list[i], next_index[i])
                    current_constraints[node] = dp_table[i][next_index[i]][0]
                    remark = remark + dp_table[i][next_index[i]][1]
            next_transition = (functools.reduce(unite_dict_return, current_constraints.values()), remark, drawing_label)
            interleavings.append(next_transition)
            current_index = next_index
        return interleavings



    #constructs stateful_node_updates
    def stateful_node_update(self, node_state_dict, flags = None):
        '''method that performs consumer demand generation and directly applies the valid interleaving to the virtual platform state.
        
        node_state_dict: dictionary that specifies desired transitions, of the form {consumer_name: desired power state }'''
        node_state_dict_copy = copy.deepcopy(node_state_dict)
        initial_dict = copy.deepcopy(node_state_dict)
        for node in self.stateful_nodes:
            if node in node_state_dict_copy:
                if node_state_dict_copy[node] == self.current_node_state[node]:
                    del node_state_dict_copy[node]
                    del initial_dict[node]
                else:
                    initial_state = [(self.nodes[node].get_most_general_states(self.current_node_state[node]), "")]
                    node_state_dict_copy[node] = initial_state + self.nodes[node].get_transition(self.current_node_state[node], node_state_dict_copy[node])
        if(node_state_dict_copy == {}):
            return #no changes required, consumers are already in requested states
        node_list = list(node_state_dict_copy.keys())
        dp_table = list(map(lambda node: node_state_dict_copy[node], node_state_dict_copy))
        self.problem.push()
        self.problem.add(self.translate_state_dict(self.extend_to_stateful_nodes({}, set(node_state_dict_copy.keys()))))
        reachable = self.determine_reachable(dp_table, True if flags is None else flags.prefer_concurrent_interleaving)
        self.problem.pop()
        sequence = self.extract_solution(*reachable)
        interleaving = self.construct_interleavings(sequence, dp_table, node_list)
        self.apply_transitions(interleaving, initial_dict, flags)


                
    
    def apply_transitions(self, interleaving, node_state_dict, flags = None):
        '''applies the interleaving found by the stateful_node_update method'''
        if flags is None:
            flags = State_Search_Flags(all_solutions = False)
        inital_ignore_nodes = flags.ignore_nodes
        flags.ignore_nodes = set.union(flags.ignore_nodes, set(node_state_dict.keys()))
        i = 1
        #for transition step in interleaving:
        for element, remark, label in interleaving:
            self.apply_changes(element, flags, label = label + "G" + str(i))
            if not remark.isspace():
                print(remark.strip())
                print("")
            i = i + 1
        flags.ignore_nodes = inital_ignore_nodes
        for node in node_state_dict:
            self.current_node_state[node] = node_state_dict[node]
        self.apply_changes({}, flags, label = ",G" + str(i))

    #-------------------------------------------------------------------------------------------

    
    def parametrized_state_search(self, wire_state_dict, flags, expected_solutions = None, label = ""):
        '''performs state generation on the consumer demands specified by wire_state_dict, parametrised by flags'''
        new_wire_state_dict = self.extend_to_stateful_nodes(wire_state_dict, flags.ignore_nodes)
        if flags.extend:
            unite_dict(new_wire_state_dict, self.most_general_state)
        
        if not flags.all_solutions: #uses present wire_state_range to determine if new search is necessary
            try:
                new_states = copy.deepcopy(self.current_wire_state)
                set_sequence = []
                monitor_sequence = []
                for name, state in new_wire_state_dict.items():
                    try:
                        new_states[name] = intersect(state, self.current_wire_state[name])
                    except State_Space_Error:
                        new_states[name] = select_state(intersect(state, self.current_wire_state_range[name]))
                        set_sequence.append("set_" + name)
                        monitor_sequence.append(name)
                sequence = [set_sequence, monitor_sequence]
                #command_string = self.construct_command_string(sequence, new_states)
                return [(copy.deepcopy(self.current_wire_state_range), new_states, 0, sequence)]
            except (State_Space_Error, KeyError, Set_Error):
                pass
        
        
        #use z3 to find a solution
        if flags.use_z3:
            constraints = self.translate_state_dict(new_wire_state_dict)
            self.problem.push()
            self.problem.add(constraints)
            if self.problem.check() == z3.sat:
                solution = self.recover_solution(self.problem.model())
                solution = self.create_update_sequence(solution, flags)
                if solution is None:
                    return [] 
                if flags.visualize:
                    self.system.visualise_sequence(solution[1], solution[3], label)
            else:
                solution = []
            self.problem.pop()
            
            return solution 
        
        #use own implementation to find a solution
        solutions = self.synthesize_wire_updates(new_wire_state_dict, flags)
        
        #visualise all solutions found
        if flags.visualize:
            current = copy.deepcopy(self.current_wire_state)

            for i in range(len(solutions)):
                l = "%s, option %d" % (label, i)
                self.system.visualise_result(current, l)
                self.system.visualise_sequence(solutions[i][1], solutions[i][3], l)
            #return to initial state
            self.system.visualise_result(current, "last applied state")
                
        #for testing
        if not expected_solutions is None:
            if len(solutions) != expected_solutions:
                raise Synthesis_Error("expected number of solutions differ! Got %d and expected %d" % (len(solutions), expected_solutions))
        return solutions


    # given a list of desired states, returns all possible update sequences
    def synthesize_wire_updates(self, wire_state_dict, flags):
        '''the implementation of our state generation procedure, find feasible state assignment(s) for consumer demands specified by wire_state_dict'''
        change_options = []
        for key in wire_state_dict:
            wire_state_dict[key] = (wire_state_dict[key], None)
        current = Synth_state(None, None, wire_state_dict, {}, [], {})
        (synth, choices) = current.state_space_search([], self, flags)
        flags.aggressive = False
        while not synth is None:
            #pass collected constraint objects to z3 solver
            avoid = None
            if synth.synth_constraints != []:
                problem = z3.Solver()
                variables = {}
                states = []
                names = []
                for varname, (wire_name, index) in synth.constrained_wires.items():
                    variables[varname] = z3.Int(varname)
                    names.append(varname)
                    states.append(synth.proposed_states[wire_name][ProposedState.State][index])
                problem.add(self.translate_state(states, names, variables))
                for function, varnames in synth.synth_constraints:
                    problem.add(function(*map(lambda var: variables[var], varnames)))
                if problem.check() == z3.sat:
                    model = problem.model()
                    for d in model.decls():
                        (wire_name, index) = synth.constrained_wires[d.name()]
                        if isinstance(synth.proposed_states[wire_name][ProposedState.State][index], set):
                            synth.proposed_states[wire_name][ProposedState.State][index] = {model[d].as_long()}
                        else:
                            synth.proposed_states[wire_name][ProposedState.State][index] = (model[d].as_long(), model[d].as_long())
                    solution = self.create_update_sequence(synth.proposed_states, flags)
                   
                    if not solution is None:
                        change_options.append(solution)
                        if flags.print_solutions:
                            print(change_options[-1][3])
                    else: 
                        print("solution is None")
                        assert(0 == 1)
                else: 
                    print("z3 failed")
            else:
                solution = self.create_update_sequence(synth.proposed_states, flags)
                if not solution is None:
                    change_options.append(solution)
                    if flags.print_solutions:
                        print(change_options[-1][3])
                else:
                    print("solution is None")
                    assert(0 == 1)
            if choices != []:
                if (not flags.all_solutions) and (change_options != []): #solution was found and only one solution required
                    synth = None #breaks loop
                else:
                    choices = synth.revert(choices, flags, self, avoid)
                    if choices is None:
                        synth = None
                    else:
                        (synth, choices) = synth.state_space_search(choices, self, flags)
            else:
                synth = None    
        return change_options

    #generates all possible state updates and selects the one that compared to the current state requires the fewest changes
    def apply_changes(self, wire_state_dict, flags = None, label = ""):
        '''calls parametrised_state_search on the given consumer demands and flags, and additionally updates the virtual platform state'''
        
        split = label.split(",")
        
        if len(split) > 1:
            label_graph = split[-1]
            label_visualisation = functools.reduce(lambda x, y: x + y, split[:-1])
        else:
            label_graph = "Graph"
            label_visualisation = split[0]
        
        if flags is None:
            flags = State_Search_Flags(print_solutions=False)

        visualise = flags.visualize
        flags.visualize = False #prevent param. from showing all solutions

        options = self.parametrized_state_search(wire_state_dict, flags)
        if options == []:
            raise Synthesis_Error(
                "could not find an update sequence for %s that results in desired values" % str(wire_state_dict))
        #if several solutions, applies solution that requires fewest updates -> the largest number of states kept the same
        updates = max(options, key=lambda x: x[2])

        if flags.return_graph:
            graph_file = open("results/eval3_%s.txt"%label_graph, 'w')
            graph_file.write(str(updates[4]))
            graph_file.close()
            

        #only construct commmand sequence once option has been selected -> construction might influence topology state!
        commands = self.construct_command_string(updates[3], updates[1])

        self.state_update(updates[0], updates[1])

        if visualise:
            self.system.visualise_sequence(updates[1], updates[3], label_visualisation)
            flags.visualize = True
        
        

        if not flags.no_output and not commands.isspace(): #if unchanged not recorded, updates[3] might be an empty string
            print(commands)
        self.commands += commands
        return(updates[0], updates[1]) #returns changes 
    
    
    #constructs command string
    def construct_command_string(self, sequence, new_states):
        '''constructs the command string from the event sequence "sequence" passed to it, which has the platform transition to a state described by "new_states"'''
        command_string = ""
        for seq in sequence:
            for s in seq:
                if s[:4] == "set_":
                    #create command for an explicit set event
                    command_string += self.wires[s[4:]].set(new_states[s[4:]]) + "\n"
                else:
                    #complete event:
                    #create command that ensures the wire state change was accomplished
                    value = new_states[s]
                    monitor_list = list(filter(lambda x: x[0], map(lambda x: x(value, new_states) , self.wires[s].monitors)))
                    if len(monitor_list) > 0:
                        command_string += "\n".join(map(lambda x: x[1], monitor_list)) + "\n"
            command_string += "#\n"
        return command_string

    def add_after_events(self, graph, name, event_set, implicit_set_events, not_changing):
        '''adds edges defined by aI (after Initiate) or aC (after Complete) to "graph":
        
        graph: event graph that is being constructed
        
        name: specifies the event of the considered conductor (that must happen "before")
        
        event_set: corresponds to aI or aC
        
        implicit_set_events: dictionary that specify resolved explicit events for every event e
        
        not_changing: wires that do not change their state from the perspective of the considered conductor'''
        for elem in event_set:
            if elem[4:] in not_changing or None in implicit_set_events[elem[4:]]:
                return None
            for event in implicit_set_events[elem[4:]]:
                graph["set_" + event] = graph.get(name, set()) | {name}
        return graph
        

    def construct_graph_from_lists(self, graph_info, implicit_set_events, current_state, remove_set):
        '''constructs the event graph from "graph_info":

        graph_info: dictionary mapping conductors to the collected information about their sequence requirements

        implicit_set_events: dictionary mapping Initiate events to their resolved explicit events
        
        current_state: the current virtual platform state assignment
        
        remove_set: set of conductors whose Initiate and Complete Events have already happened'''
        
        graph = {}
        for wire, (raw_req, (update_type, (before_set, before_complete, after_set, after_complete), _)) in graph_info.items():
            set_w = "set_" + wire
            #wire states that are not changing from point of view of wire
            not_changing = set(filter(lambda x: not empty_intersection(x, raw_req, current_state), raw_req.keys()))
            if update_type == SET.Explicit:
                graph[wire] = graph.get(wire, set()) | {set_w}
                graph[set_w] = graph.get(set_w, set()) | (before_set - (remove_set & not_changing))
                graph = self.add_after_events(graph, set_w, after_set, implicit_set_events, not_changing)
                if graph is None:
                    return None
            else:
                #complete of wire happens after implicit set of wire
                graph[wire] = graph.get(wire, set()) | (implicit_set_events[wire] - {None})
                #do after and before sets
                for event in (implicit_set_events[wire] - {None}):
                    graph["set_" + event] = graph.get("set_" + event, set()) | (before_set - (remove_set & not_changing))
                    graph = self.add_after_events(graph, "set_" + event, after_set, implicit_set_events, not_changing)
                    if graph is None:
                        return None

            graph[wire] = graph.get(wire, set()) | (before_complete - (remove_set & not_changing))
            graph = self.add_after_events(graph, wire, after_complete, implicit_set_events, not_changing)
            if graph is None:
                return None
        return graph

    #dependencies is a dictionary wire_name -> (raw_req, dependency)
    #only contains entries for wires whose state is going to change
    def construct_implicit_set_events(self, dependencies, new_state, remove_set):
        '''resolves implicit Initiate events to sets of explicit Initiate events'''
        file_object = open('set_events.txt', 'a')
        implicit_set_events = dict(map(lambda x: (x[0], x[1][1][2](new_state)[x[0]]), dependencies.items()))
        file_object.write("\n\n\n" + str(implicit_set_events) + "\n")
        sequence = topological_sort(implicit_set_events)
        
        for wire in self.wires:
            #avoid key errors if already happened events are referenced
            #every implicit state that references an already happened event will contain "None"
            implicit_set_events[wire] = implicit_set_events.get(wire, {None})
        if sequence != []:
            for event in sequence[0]:
                #others are "already happened implicit sets" 
                #usually in remove set, but present in very first generated state)
                #just leave them
                if event in dependencies and dependencies[event][1][0] == SET.Explicit:
                    #explicit events
                    implicit_set_events[event] = {event}
                else:
                    #if already happened event is referenced, None as element
                    #handle differently if all or any event (if support added)
                    #print(event)
                    implicit_set_events[event] = {None}
            for sublist in sequence[1:]:
                for elem in sublist:
                    implicit_set_events[elem] = set().union(*map(lambda x: implicit_set_events[x], implicit_set_events[elem]))
        
        file_object.write(str(implicit_set_events) + "\n")

        file_object.close()
        return implicit_set_events


    #creates update sequence given by the propsed states
    #performs comparison to current state

    def create_update_sequence(self, proposed_states, flags): #record_unchanged = True, wire_states = None):
        '''creates a command sequence that implements the transition of the platform to some platform state described by the state space mapping "proposed states"'''
        new_state_range = {}
        new_states = {}
        #superstates = [] #used only in "synthesize state updates" (updates states of stateful nodes)
        keep_states = 0
        change_strings = {}
        dependencies = {}#[]
        graph = {}
        remove_from_graph = set()

        #construct "new_states": select a single state from a state range/set to be realised by the system
        #remove_from_graph contains wires whose state is not required to change
        for wire, (value, _, dependency, raw_req) in proposed_states.items(): 
            new_state_range[wire] = value
            try:
                current_state = self.current_wire_state[wire]
                if current_state == [{1}] and (value == [{0, 1}] or value == [{1, 0}]): 
                    #prevent logical wires from being kept enabled
                    new_states[wire] = [{0}]
                    dependencies[wire] = (raw_req, dependency)
                    #graph.update({wire: dep | graph.get(wire, set()) for wire, dep in dependency.items()})
                    change_strings[wire] = "set wire %s to value: %s\n" % (wire, str(new_states[wire]))
                else:
                    new_value = intersect(current_state, value)
                    keep_states += 1
                    remove_from_graph = remove_from_graph | {wire, "set_" + wire}
                    new_states[wire] = select_state(new_value)
            except (State_Space_Error, KeyError):
                new_states[wire] = select_state(value)
                dependencies[wire] = (raw_req, dependency)
                #graph.update({wire: dep | graph.get(wire, set()) for wire, dep in dependency.items()})
                change_strings[wire] = "set wire %s to value: %s\n" % (wire, str(new_states[wire]))

        implicit_events = self.construct_implicit_set_events(dependencies, new_states, remove_from_graph)
        graph = self.construct_graph_from_lists(dependencies, implicit_events, self.current_wire_state, remove_from_graph)
        graph_copy = copy.deepcopy(graph)
        

        sequence = topological_sort(graph)

        if sequence is None:
            #there is no feasible sequence of commands;
            #None signals that solution this method was supposed to create is infeasible
            return None

        sequence = list(map(lambda seq: list(filter(lambda x: x not in remove_from_graph, seq)), sequence))

        #command_string = self.construct_command_string(sequence, new_states)

        return (new_state_range, new_states, keep_states, sequence, graph_copy)




class Synthesis_Error(Exception):
    def __init__(self, msg):
        self.msg = msg


def max_none(c1, c2):
    if c1 is None:
        return c2
    elif c2 is None:
        return c1
    else:
        return max(c1, c2)


class Synth_state(object):
    '''a class used to store previous execution states for backtracking purposes'''
    def __init__(self, state, wire, wire_state_dict, proposed_states, synth_constraints, constrained_wires, choice = None):
        self.state =state
        self.wire = wire
        self.wire_state_dict = wire_state_dict
        self.proposed_states = proposed_states
        self.synth_constraints = synth_constraints
        self.constrained_wires = constrained_wires
        self.choice = choice


    def str(self):
        return self.wire.name

    #creates a new Synth_state with all the currently collected information to fall back to later on
    def snapshot(self):
        '''return a new Synth_state instance that is an exact copy of self'''
        return Synth_state(copy.deepcopy(self.state), self.wire, copy.deepcopy(self.wire_state_dict), copy.deepcopy(self.proposed_states), copy.deepcopy(self.synth_constraints), copy.deepcopy(self.constrained_wires), copy.deepcopy(self.choice))

    
    
    #updates the Synth_state with the choice of a wire state
    def process_choice(self, choice, choice_index, flags):
        '''update the synth_state instance with the requirements associated with a chosen state possibility "choice"'''
        (state, constraints, complex_constraints, dependency) = choice
        choice_index = max_none(choice_index, self.wire_state_dict[self.wire.name][WireState.Index]) #remember last choice this wire was involved in
        del self.wire_state_dict[self.wire.name]
        if not self.wire.name in self.proposed_states:
            self.proposed_states[self.wire.name] = (state, choice_index, dependency, constraints)
        else:
            raise Synthesis_Error(
                "internal datastructures are in an erroneous state")
        if complex_constraints != []:
            for fun, variables in complex_constraints:
                new_names = []
                for name, index in variables:
                    #name = getattr(self.wire.output_device, pinname).name
                    new_name = name + str(index)
                    new_names.append(new_name)
                    self.constrained_wires[new_name] = (name, index)
                    self.synth_constraints.append((fun, (new_names)))
        fallback = {}
        success = True
        #see if constraints of choice can be enforced
        for (wire_name, state) in constraints.items():
            #wire_name = getattr(self.wire.output_device, name).name
            rival_state = None
            rival_choice = None
            proposed = False
            if wire_name in self.wire_state_dict:
                (rival_state, rival_choice) = self.wire_state_dict[wire_name]
            if wire_name in self.proposed_states:
                proposed = True
                rival_choice = max_none(rival_choice, self.proposed_states[wire_name][ProposedState.Index])
                if not rival_state is None:
                    raise Synthesis_Error("erroneous state")
                rival_state, rival_choice, rival_dependency, raw_req = self.proposed_states[wire_name]
            if not rival_state is None:
                c = max_none(choice_index, rival_choice)
                try:
                    if proposed:
                        self.proposed_states[wire_name] = (intersect(rival_state, state), c, rival_dependency, raw_req)
                    else:
                        self.wire_state_dict[wire_name] = (intersect(rival_state, state), c)  #.append((wire_name, state))
                except State_Space_Error:
                    #print("failed because of: " + wire_name + str(rival_state))
                    success = False
                    if not flags.advanced_backtracking:
                        break
                    fallback[wire_name] = rival_state
            else:
                self.wire_state_dict[wire_name] = (copy.deepcopy(state), choice_index)
        return (success, fallback)

    def fallback_synth(self, revert):
        '''revert to the execution state stored by a synth_state snapshot'''
        self.state = copy.deepcopy(revert.state)
        self.wire = revert.wire
        self.wire_state_dict = copy.deepcopy(revert.wire_state_dict)
        self.proposed_states = copy.deepcopy(revert.proposed_states)
        self.synth_constraints = copy.deepcopy(revert.synth_constraints)
        self.constrained_wires = copy.deepcopy(revert.constrained_wires)
        self.choice = copy.deepcopy(revert.choice)

    #return -2 if key not present in wire_state_dict and proposed states
    #return -1 if key is None in either/both wire_state_dict / proposed states
    def return_index(self, key):
        '''return the largest index of choices at which the required state of conductor "key" was updated. Returns -2 if the state of key has not yet been restricted by the produced and -1 if last restriction was imposed by original consumer demands'''
        value = -2 #return -2 if key not present in wire_state_dict and proposed states
        if key in self.wire_state_dict:
            value = max_none(self.wire_state_dict[key][WireState.Index], -1)
        if key in self.proposed_states:
            value = max_none(self.proposed_states[key][ProposedState.Index], max(value, -1))
        return value

    #revert helper methods used when advanced backtracking is enabled
    #-----------------------------------------------------------------------------------------------
    def find_next_index(self, avoid, all_solutions):
        '''uses return_index method to find the next choices index to try'''
        indices = list(map(lambda x: self.return_index(x), avoid))
        if indices == [] or min(indices) == -2:
            return -1
        elif max(indices) == -1:
            return None
        else:
            return max(indices)


    def wire_could_change(self, wire, state):
        '''decides if according to the current execution state, the state restrictions of the conductor "wire" could be different from "state"'''
        if wire in self.wire_state_dict and state != self.wire_state_dict[wire][WireState.State]:
            return True
        elif wire in self.proposed_states and state != self.proposed_states[wire][ProposedState.State]:
            return True
        elif not wire in self.wire_state_dict and not wire in self.proposed_states:
            return True
        else:
            return False


    def worth_a_try(self, avoid, current_choice, could_change, consider_conditions):
        '''decides if a given State Possibility might resolve issue encountered'''
        wire = self.wire.name
        worth_a_try = False
        if wire in avoid:
            try:
                intersection = intersect(current_choice[0], avoid[wire])
                if intersection != current_choice[0]:
                    return True
            except State_Space_Error:
                return True
        if consider_conditions:
            #output = self.wire.output_device
            copy_could_change = copy.deepcopy(could_change)
            for (wire_name, state) in current_choice[1].items(): #conditions of current choice
                #wire_name = getattr(output, name_input).name
                if wire_name in could_change:
                    copy_could_change.remove(wire_name)
                    avoid_state = avoid[wire_name]
                    try:
                        new_state = intersect(state, avoid_state)
                        if new_state != state:
                            return True
                    except State_Space_Error:
                            return True
            if len(copy_could_change) != 0:
                worth_a_try = True
        return worth_a_try


    #--------------------------------------------------------------------------------------------------

    #fall back to a previous synth_state object
    #avoid: wire: state dict of wire states to avoid
    def revert(self, choices, flags, topology, avoid = None):
        '''reverts to a previous execution state, either naively if avoid = None or to an execution state where the contradicting restrictions given by "avoid" can be avoided'''
        finished = False
        if not flags.advanced_backtracking:
            avoid = None
        while not finished: #new choice might fail already when processed, must keep trying until it succeeds or no more choices left
            if(len(choices) == 0):
                return None
            else:
                if avoid is None:
                    revert = choices.pop(-1)
                    while len(revert[0]) > 0:
                        self.fallback_synth(revert[1])
                        current_choice = revert[0].pop(0)
                        length = len(choices)
                        if len(revert[0]) == 0: #have used all choices we had
                            length = length - 1
                        (finished, _) = self.process_choice(current_choice, length, flags)
                        if finished:
                            break
                else:
                    index = self.find_next_index(avoid.keys(), flags.all_solutions)

                    if index == -1: #we have already exhausted all possibilities that could have solved the conflict; revert "normally"
                        avoid = None
                        continue
                    if index is None:
                        return None
                    choices = choices[:index+1]
                    revert = choices.pop(-1)
                    self.fallback_synth(revert[1])
                    could_change = list(filter(lambda x: self.wire_could_change(*x), avoid.items()))
                    #print(could_change)
                    consider_conditions = len(could_change) > 0
                    number_of_still_available_choices = len(revert[0])
                    while len(revert[0]) > 0:
                        current_choice = revert[0].pop(0)
                        worth_a_try = self.worth_a_try(avoid, current_choice, could_change, consider_conditions)
                        if worth_a_try:
                            length = len(choices)
                            if len(revert[0]) == 0:
                                length = length - 1
                            finished, _ = self.process_choice(current_choice, length, flags)
                            if finished:
                                break
                            self.fallback_synth(revert[1])
                    next_index = self.find_next_index(avoid, flags.all_solutions)
                    if (not finished) and (not flags.aggressive) and (next_index is None or len(choices) > next_index):
                        already_tried_choices = copy.deepcopy(self.choice[:len(self.choice) - number_of_still_available_choices])
                        while len(already_tried_choices) > 0:
                            current_choice = already_tried_choices.pop(0)
                            worth_a_try = self.worth_a_try(avoid, current_choice, could_change, consider_conditions)
                            if worth_a_try:
                                finished, _ = self.process_choice(current_choice, None, flags)
                                self.fallback_synth(revert[1])
                                if not finished:
                                    pass 
                                else:
                                    finished = False
                                    avoid = None
                                    break

            if len(revert[0]) > 0:
                choices.append(revert) 
        return choices
    
    #given desired wire states, generates possible state choices and remembers them
    def state_space_search(self, choices, topology, flags):
        '''implements a single iteration of the state generation procedure'''
        while len(self.wire_state_dict) != 0:
            wire = min(self.wire_state_dict.keys(), key = topology.wire_sort_function) #extracts next desired state to enforce
            #self.state = self.wire_state_dict.pop(wire)
            self.state = self.wire_state_dict[wire]
            w = topology.wires[wire]
            self.wire = w
            if wire in self.proposed_states:
                raise Synthesis_Error("erroneous state")
            else:
                self.choice = possible(self.state[0], w.constraints)
                if(len(self.choice) == 0):
                    #print("conflict" + str(self.wire.name) + str(self.state))
                    if(len(choices) == 0):
                        return(None, [])
                    choices = self.revert(choices, flags, topology, {self.wire.name : self.state[0]})
                    if choices is None:
                        return(None, [])
                else:
                    fallback = self.snapshot()
                    avoid = {}
                    success = False
                    choice = copy.deepcopy(self.choice)
                    while(len(choice) > 0):
                        length = len(choices)
                        current_choice = choice.pop(0)
                        if len(choice) == 0:
                            length = length - 1
                        success, failure_set = self.process_choice(current_choice, length, flags)
                        state_union_dict(avoid, failure_set)
                        if success:
                            break
                        else:
                            self.fallback_synth(fallback)
                    if len(choice) > 0:
                        choices.append((choice, fallback))
                    elif not success:
                        state_union_dict(avoid, {w.name : self.state[0]})
                        if len(choices) == 0:
                            return (None, [])
                        else:
                            choices = self.revert(choices, flags, topology, avoid)
                            if choices is None:
                                return (None, [])
        return(self, choices)