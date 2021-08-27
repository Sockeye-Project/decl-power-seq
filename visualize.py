try:
    from pygraphviz import AGraph
    global_visualise = True
    from pynput.keyboard import Key, Listener
except ImportError:
    print("unable to import graph drawing library, no output will be produced")
    global_visualise = False
import subprocess
#pylint: disable = no-member



class System(object):

    default_graphattr = {"directed" : True, "strict" : False, "ranksep" :  3, "splines": False, "rankdir": "LR", "fontsize" : 30, "labelloc" : "t"}

    #nodes: dictionary: {name: (node_label, attr)}
    #wires: dictionary: {name : (output_node, output_port,  {input_node, input_port}, wire_type)}
    def __init__(self, nodes, wires, graph_attr = {}):
        if global_visualise:
            self.prev_key = None
            self.default_graphattr.update(graph_attr)
            self.graph = AGraph(**self.default_graphattr)
            self.wires = {}

            self.current_state = {}

            for name, (output_node, output_port, input_set, wire_type) in wires.items():
                wire_list = []
                self.current_state[name] = ("         ", "black")
                if len(input_set) > 1:
                    self.graph.add_node(name, shape = "point", width = 0, contraint = False)
                    self.graph.add_edge(output_node, name, tailport = output_port + ":e", label = "        ", arrowhead = "none", penwidth = 4)
                    wire_list.append((output_node, name))
                    for input_node, input_port in input_set:
                        wire_list.append((name, input_node, input_port))
                        self.graph.add_edge(name, input_node, key = input_port, headport = input_port + ":w", penwidth = 2)
                elif len(input_set) == 1:
                    input_node, input_port = list(input_set)[0]
                    wire_list.append((output_node, input_node, input_port))
                    self.graph.add_edge(output_node, input_node, key = input_port, headport = input_port + ":w", tailport = output_port + ":e", label = "       ", penwidth = 4, minlen = 2)
                self.wires[name] = [wire_list, wire_type, output_node]

            for name, (node_label, attr) in nodes.items():
                self.graph.add_node(name, label = node_label, shape = "record", **attr)

            

            self.main_queue = [("", {}, {})]
            self.current_index = 0

            self.graph.layout(prog="dot")
            self.graph.draw("system.pdf", args="-Kneato -n2", prog = "dot")
            subprocess.Popen("system.pdf", shell = True)


            self.node_positions = set()
            for w in self.wires.values():
                out_node = w[2]
                out_pos = self.graph.get_node(out_node).attr["pos"]
                out_pos = float(out_pos.split(',')[0])
                w[2] = out_pos
                self.node_positions.add(out_pos)
            self.node_positions = sorted(list(self.node_positions))
            for w in self.wires.values():
                w[2] = self.node_positions.index(w[2])
            
            self.listener = Listener(on_press = lambda key: self.on_press(key))#lambda key, system = self: system.on_press(key))
            self.listener.start()
        else:
            pass

        



    def colour(self, state, x_pos):
        wire_hue = x_pos * (120 / (len(self.node_positions) - 1))
        if list(state[0])[0] == 0:
            return "%.3f 1.000 1.000" % (((284 + wire_hue) % 360) / 360)
        else:
            return "%.3f 1.000 1.000" % (((120 + wire_hue) % 360) / 360)

    @staticmethod
    def describe(state, wire_type):
        if wire_type == "logical" or wire_type == "bus":
            return str(list(state[0])[0])
        elif wire_type == "power":
            return str(list(state[0])[0]) + " mV"
        elif wire_type == "clock":
            return "clk"
        else:
            raise AttributeError("unknown wire_type")


    def visualise_result(self, states, label):
        if global_visualise:
            change_dicts = [{}, {}]
            for w_name, state in states.items():
                _, w_type, w_xpos = self.wires[w_name]
                new_label = self.describe(state, w_type)
                new_colour = self.colour(state, w_xpos)
                old_label, old_colour = self.current_state[w_name]
                self.current_state[w_name] = (new_label, new_colour)
                change_dicts[0][w_name] = (new_label, new_colour) 
                change_dicts[1][w_name] = (old_label, old_colour)
            self.main_queue.append((label, change_dicts[0], change_dicts[1]))
        else:
            pass


    
    
    def visualise_sequence(self, states, sequence, label):
        if global_visualise:
            if len(sequence) == 0:
                self.main_queue.append((label, {}, {}))
            for i in range(len(sequence)):
                seq_label = label + " simultaneous actions" + str(i)
                for elem in sequence[i]:
                    if elem[:4] == "set_":
                        w_name = elem[4:]
                    else:
                        w_name = elem
                    w_list, w_type, w_xpos = self.wires[w_name]
                    graph_edge = self.graph.get_edge(*w_list[0])
                    old_label, old_colour = self.current_state[w_name]
                    state = states[w_name]
                    new_label = self.describe(state, w_type)
                    if w_name == elem:
                        new_colour = self.colour(state, w_xpos)
                    else:
                        new_colour = "yellow"
                    self.current_state[w_name] = (new_label, new_colour)
                    self.main_queue.append((seq_label, {w_name : (new_label, new_colour)}, {w_name :(old_label, old_colour)}))
        else:
            pass

    def draw(self, label, change_dict):
        self.graph.graph_attr["label"] = label
        for name, (label, colour) in change_dict.items():
            w_list = self.wires[name][0]
            for i in range(len(w_list)):
                if i == 0:
                    self.graph.get_edge(*w_list[0]).attr['label'] = label
                self.graph.get_edge(*w_list[i]).attr['color'] = colour
        self.graph.draw("system.pdf", args="-Kneato -n2", prog= "dot")

    def on_press(self, key):
        if key == Key.right and self.current_index + 1 < len(self.main_queue):
            self.current_index += 1
            label, change_dict, _ = self.main_queue[self.current_index]
            self.draw(label, change_dict)
        if key == Key.left and self.current_index > 0:
            change_dict = self.main_queue[self.current_index][2]
            label = self.main_queue[self.current_index - 1][0]
            self.draw(label, change_dict)
            self.current_index -= 1
        if key == Key.end:
            change_dict = {}
            length = len(self.main_queue)
            for i in range(self.current_index + 1, length):
                change_dict.update(self.main_queue[i][1])
            label = self.main_queue[-1][0]
            self.draw(label, change_dict)
            self.current_index = length - 1
        if key == Key.up and self.current_index < len(self.main_queue):
            if self.prev_key == Key.down and self.current_index != 0:
                self.current_index += 1
            label = self.main_queue[self.current_index][0]
            change_dict = {}
            while self.current_index < len(self.main_queue) and label == self.main_queue[self.current_index][0]:
                label, cdict, _ =  self.main_queue[self.current_index]
                change_dict.update(cdict)
                self.current_index += 1
            if self.current_index == len(self.main_queue):
                self.current_index -= 1
            self.draw(label, change_dict)
        if key == Key.down and self.current_index > 0:
            if self.prev_key == Key.up and self.current_index != len(self.main_queue)-1:
                self.current_index -= 1
            label = self.main_queue[self.current_index][0]
            change_dict = {}
            while self.current_index >= 0 and label == self.main_queue[self.current_index][0]:
                label, _, cdict = self.main_queue[self.current_index]
                change_dict.update(cdict)
                self.current_index -= 1
            if self.current_index == -1:
                self.current_index = 0
            label = self.main_queue[self.current_index][0]
            self.draw(label, change_dict)

        if key == Key.esc:
            return False
        self.prev_key = key

    def done(self):
        if global_visualise:
            print("Press \u2192 to jump to the next change in the sequence\n")
            print("Press \u2190 to return to the previous change in the sequence\n")
            print("Press \u2191 to jump to the next change sequence\n")
            print("Press \u2193 to return to the last change sequence\n")
            print("Press 'End' to skip to the end of the visualisation\n")
            print("Press 'Esc' to terminate the visualisation\n")
            self.listener.join()
        else:
            pass

