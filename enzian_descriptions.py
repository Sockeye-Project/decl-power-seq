from sequence_generation import Node, Input, Output, Constraint, Wire, PowerState, Stateful_Node, intersect, State_Space_Error, unite_dict, state_union, SET, empty_intersection
import math
from functools import partial
import z3

class INA226(Node):
    BUS = Input([{0, 1}], "bus")
    VS = Input([(0, 6000)], "power")
    VBUS = Input([(0, 40000)], "monitor", lambda node, name: node.ina_monitor(name))

    def __init__(self, name, bus_addr, device):
        self.device = device
        super(INA226, self).__init__(name, bus_addr, INA226)
        self.configured = False

    def ina_monitor(self, wire_name):
        def fun(value, states, node=self, wire=wire_name):
            if states[node.VS.name][0][0] > 2700 and states[node.VS.name][0][0] < 5500:
                commands = node.configure()
                commands.append("wait_for_voltage('%s', v_min=%.3f, v_max=%.3f, device='%s', monitor='VOLTAGE')" % (
                    wire,
                    0.00095 * list(value[0])[0],
                    0.00105 * list(value[0])[0],
                    node.device
                ))
                return (True, "\n".join(commands))
            else:
                return (False, "wait_for_voltage('%s', v_min=%.3f, v_max=%.3f, device='%s', monitor='VOLTAGE')" % (
                    wire,
                    0.00095 * list(value[0])[0],
                    0.00105 * list(value[0])[0],
                    node.device
                ))
        return fun

    def configure(self):
        if self.configured:
            return []
        else:
            self.configured = True
            return [
                "init_device('%s', False)" % (self.device)
            ]

class MAX15301(Node):
    implicit_off = {"EN": [{0}], "V_PWR": [(0, 4400)]}
    implicit_on = {"EN": [{1}], "V_PWR": [(5500, 14000)]}
    BUS = Input([{0, 1}], "bus")
    EN = Input([{0, 1}], "logical")
    V_PWR = Input([(0, 14000)], "power")
    V_OUT = lambda default : Output([(0, 5250)],
                            [Constraint([], {"EN": [{1}], "V_PWR": [(5500, 14000)]}, partial(Constraint.implicit, "V_OUT", MAX15301.implicit_on), state_update = Constraint.default_state),
                            Constraint([(600, 5250)], {"EN": [{1}], "V_PWR": [(5500, 14000)], "BUS" : [{1}]}, {}, dependency_update=(Constraint.is_default, [partial(Constraint.explicit, "V_OUT", {"V_PWR", "BUS"}, {"EN"}, after_set = {"EN"}), partial(Constraint.explicit, "V_OUT", {"V_PWR", "BUS", "EN"}, set())])), 
                            Constraint([(0, 0)], {"EN": [{0}], "V_PWR": [(0, 14000)]}, partial(Constraint.implicit, "V_OUT", MAX15301.implicit_off))
                            ], "power", Wire.voltage_set)

    def __init__(self, name, bus_addr, default, device):
        self.device = device
        self.default = default
        self.is_default = False
        self.current = [(default, default)]
        self.V_OUT = MAX15301.V_OUT(default)
        super(MAX15301, self).__init__(name, bus_addr, MAX15301)

    def bus_req(self):
        return {self.V_PWR.name: [(5500, 14000)]}

    def bus_req_off(self):
        return {self.V_PWR.name: [(0, 4400)]}


    def update(self, states):
        try:
            intersect(states[self.V_OUT.name], [(600, 5250)])
            self.current = states[self.V_OUT.name]
            self.is_default = True
            return
        except State_Space_Error:
            self.is_default = False
        try:
            intersect(states[self.V_PWR.name], [(0, 4400)])
            self.current = [(self.default, self.default)]
            return
        except State_Space_Error:
            pass



        



class NCP(Node):
    implicit_on = {"VRI" : [(868, 3600)], "VCC" : [(2375, 5500)]}
    implicit_off = {"VRI" : [(0, 868)], "VCC" : [(0, 2374)]}
    VCC = Input([(0, 6000)], "power")
    VRI = Input([(0, 6000)], "power") #reference input
    VREF = Output([(0, 6000)], 
                     [Constraint([(435, 1800)], {"VRI" : [(868, 3600)], "VCC" : [(2375, 5500)]}, partial(Constraint.implicit, "VREF", "implicit_on"), complex_constraints= [(lambda x1, x2: z3.Or(x1 * 2 == x2, x1 * 2 == x2 + 1), ([("VREF", 0), ("VRI", 0)]))]),
                        Constraint([(0, 0)], {"VRI" : [(0, 868)], "VCC" : [(2375, 5500)]}, partial(Constraint.implicit, "VREF", "implicit_off")),
                        Constraint([(0, 0)], { "VRI" : [(0, 3600)], "VCC" : [(0, 2374)]}, partial(Constraint.implicit, "VREF", "implicit_off"))], "power")

    def __init__(self, name, bus_addr):
        super(NCP, self).__init__(name, bus_addr, NCP)


class MAX8869(Node):
    implicit_on = lambda _, thresh: {"V_IN" : [(max(thresh + 500, 2700), 5500)], "SHDN" : [{1}]}
    implicit_off = lambda _, thresh: {"V_IN" : [(0, max(thresh + 499, 2699))], "SHDN" : [{0}]}
    V_IN = Input([(0, 6000)], "power")
    SHDN = Input([{0, 1}], "logical")
    V_OUT = lambda _, default, thresh: Output([(0, thresh)],
                            [Constraint([(default, default)], {"V_IN" : [(max(thresh + 500, 2700), 5500)], "SHDN" : [{1}]}, partial(Constraint.implicit, "V_OUT", "implicit_on")),
                            Constraint([(0, 0)], {"V_IN" : [(0, 5500)], "SHDN" : [{0}]}, partial(Constraint.implicit, "V_OUT", "implicit_off")),
                            ], "power")

    def __init__(self, name, bus_addr, voltage):
        self.implicit_on = self.implicit_on(int(voltage * 1.01))
        self.implicit_off = self.implicit_off(int(voltage * 1.01))
        self.V_OUT = self.V_OUT(int(voltage), int(voltage * 1.01))
        super(MAX8869, self).__init__(name, bus_addr, MAX8869)


class MAX15053(Node):
    implicit_on = lambda _, threshold: {"V_IN" : [(max(int(threshold * 1.06), 2700), 5500)], "V_EN" : [{1}]}
    implicit_off = lambda _, threshold: {"V_IN" : [(0, (max(int(threshold * 1.06) - 1, 2699)))], "V_EN" : [{0}]}
    V_IN = Input([(0, 6000)], "power")
    V_EN = Input([{0, 1}], "logical")
    V_OUT = lambda _, default, threshold: Output([(0, default)],
                            [Constraint([(default, default)], {"V_IN" : [(max(int(threshold * 1.06), 2700), 5500)], "V_EN" : [{1}]}, partial(Constraint.implicit, "V_OUT", "implicit_on")),
                            Constraint([(0, 0)], {"V_IN" : [(0, 5500)], "V_EN" : [{0}]}, partial(Constraint.implicit, "V_OUT", "implicit_off")),
                            ], "power")

    def __init__(self, name, bus_addr, voltage):
        self.implicit_on = self.implicit_on(int(voltage * 1.01))
        self.implicit_off = self.implicit_off(int(voltage * 1.01))
        self.V_OUT = self.V_OUT(voltage, int(voltage * 1.01))
        super(MAX15053, self).__init__(name, bus_addr,  MAX15053)


def binary_multidimensional(decimal):
    binary = bin(decimal)[2:] #remove 0b prefix
    multidim = list({0} for i in range(8 - len(binary)))
    for i in binary:
        multidim.append({int(i)})
    return multidim

def isl_outputs():
    outputs = []
    for i in range(0, 177):
        voltage_min = math.floor(1600 - i * 6.25)
        voltage_max = math.ceil(1600 - i * 6.25)
        outputs.append(
            Constraint(
                [(voltage_min, voltage_max)], \
                {"VID" : binary_multidimensional(i + 2),  "VCC" : [(4750, 5250)], "EN_PWR" : [{1}], "EN_VTT" : [(870, 14000)]}, {}, \
                dependency_update= (Constraint.is_default, \
                    [partial(Constraint.implicit, "VOUT", {"VID" : binary_multidimensional(i + 2)}, after_set={"EN_PWR"}, before_complete= {"VCC", "EN_VTT", "EN_PWR"}), 
                    partial(Constraint.implicit, "VOUT", {"VID" : binary_multidimensional(i + 2)}, before_complete= {"VCC", "EN_VTT", "EN_PWR"})])))
    outputs.append(Constraint([(0, 0)], {"VID": [{0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}], "VCC" : [(0, 5250)], "EN_PWR" : [{0}], "EN_VTT" : [(0, 14000)]}, partial(Constraint.implicit, "VOUT", "implicit_off")))
    return outputs


        

class ISL(Node):
    implicit_off = {"VCC" : [(0, 4300)], "EN_PWR" : [{0, 1}], "EN_VTT" : [(0, 830)]}
    VCC = Input([(0, 6000)], "power")
    EN_PWR = Input([{0, 1}], "logical") 
    EN_VTT = Input([(0, 12000)], "power")
    VID = Input([{0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}], "logical")
    VOUT = Output([(0, 1600)], isl_outputs(), "power")

    def __init__(self, name, bus_addr):
        self.is_default = False
        super(ISL, self).__init__(name, bus_addr, ISL)

    def update(self, states):
        try:
            intersect(states[self.VOUT.name], [(500, 1600)])
            self.is_default = True
        except State_Space_Error:
            self.is_default =  False



class IR(Node):
    implicit_off = lambda _, thresh : {"VCC" : [(0, 2500)], "VIN" : [(0, thresh-1)], "EN" : [{0}]}
    implicit_off_2 = lambda _, thresh : {"VCC" : [(0, 2500)], "VIN" : [(0, thresh-1)], "EN_2" : [{0}]}
    device = "ir3581"
    bus = "power"
    BUS = Input([{0, 1}], "bus")
    #loop 1 and loop 2 will have different addresses...
    VCC = Input([(0, 4000)], "power")
    EN = Input([{0, 1}], "logical")
    EN_2 = Input([{0, 1}], "logical")
    VIN = Input([(0, 13200)], "power")
    VOUT = lambda _, thresh : Output([(0, 3040)], 
                                [Constraint([(500, 3040)], {"VCC" : [(2900, 3630)], "VIN" : [(thresh, 13200)], "EN" : [{1}], "BUS": [{1}]}, {}, dependency_update = (Constraint.is_default, [partial(Constraint.explicit, "VOUT", {"VCC", "VIN", "BUS"}, {"EN"}, after_set = {"EN"}), partial(Constraint.explicit, "VOUT", {"VCC", "VIN", "BUS", "EN"}, set())])),
                                Constraint([(0, 0)], {"VCC" : [(0, 3630)], "VIN" : [(0, 13200)], "EN" : [{0}]}, partial(Constraint.implicit, "VOUT", "implicit_off")),
                                ], "power", Wire.ir_set)
    
    VOUT_2 = lambda _, thresh : Output([(0, 3040)], 
                                [Constraint([(500, 3040)], {"VCC" : [(2900, 3630)], "VIN" : [(thresh, 13200)], "EN_2" : [{1}], "BUS" : [{1}]}, {}, dependency_update = (Constraint.is_default, [partial(Constraint.explicit, "VOUT_2", {"VCC", "VIN", "BUS"}, {"EN_2"}, after_set = {"EN_2"}), partial(Constraint.explicit, "VOUT_2", {"VCC", "VIN", "BUS", "EN_2"}, set())])),
                                Constraint([(0, 0)], {"VCC" : [(0, 3630)], "VIN" : [(0, 13200)], "EN_2" : [{0}]}, partial(Constraint.implicit, "VOUT_2", "implicit_off_2")),
                                ], "power", Wire.ir_set)
    
    def __init__(self, name, bus_addr, threshold, device, loop1, loop2, l1_addr, l2_addr):
        self.configured = False
        self.is_default = False
        self.threshold = threshold
        self.device = device
        self.loop1 = loop1
        self.loop2 = loop2
        self.l1_addr = l1_addr
        self.l2_addr = l2_addr
        self.implicit_off = self.implicit_off(threshold)
        self.implicit_off_2 = self.implicit_off_2(threshold)
        self.VOUT = self.VOUT(threshold)
        self.VOUT_2 = self.VOUT_2(threshold)
        super(IR, self).__init__(name, bus_addr, IR)

    def bus_req(self):
        return {self.VIN.name : [(self.threshold, 13200)], self.VCC.name : [(2900, 3630)]}

    def bus_req_off(self):
        return {self.VIN.name : [(0, self.threshold-1)], self.VCC.name : [(0, 2500)]}

    def update(self, states):
        try:
            intersect(states[self.VOUT.name], [(500, 3040)])
            self.is_default = True
        except State_Space_Error:
            self.is_default = False
        try:
            intersect(states[self.VIN.name], [(self.threshold, 13200)])  
        except State_Space_Error:
            self.configured = False
            return
        try:
            intersect(states[self.VCC.name], [(2900, 3630)])
        except State_Space_Error:
            self.configured = False
            return

    def configure(self):
        if self.configured:
            return []
        else:
            self.configured = True
            return [
                "init_device('%s', False)" % self.device,
                "init_device('%s', False)" % self.loop1,
                "init_device('%s', False)" % self.loop2
            ]  
        

class FPGA(Stateful_Node):
    CLK = Input([(0, 0), (3300, 3300), (0, 50)], "clock")
    CLK_OK = Input([{0, 1}], "logical")
    VCCO_2V5_DDR24 = Input([(0, 3400)], "power")
    VCCO_2V5_DDR13 = Input([(0, 3400)], "power")
    VCCO_VCC_DDR24 = Input([(0, 3400)], "power")
    VCCO_VTT_DDR13 = Input([(0, 2000)], "power") #replace VREF
    VCCO_VTT_DDR24 = Input([(0, 2000)], "power")
    VCCO_VCC_DDR13 = Input([(0, 3400)], "power")
    VADJ_1V8 = Input([(0, 2000)], "power") #not found in fpga boot sequ; filled in like VCCO_VCC_DDR voltages
    MGTVCCAUX_L = Input([(0, 1900)], "power")
    MGTVCCAUX_R = Input([(0, 1900)], "power")
    VCCO_1V8 = Input([(0, 2000)], "power") #this is sys_1v8....
    VCCINT = Input([(0, 1000)], "power")
    MGTAVCC = Input([(0, 1000)], "power")
    MGTAVTT = Input([(0, 1300)], "power")
    VCCINT_IO = Input([(0, 1000)], "power")
    VCCAUX = Input([(0, 2000)], "power")
    

    states = (lambda clk, ok, vcc, io, aux, vcco, vadj, vcc_2v5_ddr13, vcc_2v5_ddr24, vcc_ddr13, vcc_ddr24, vtt_ddr13, vtt_ddr24, vtt, mgtaux_l, mgtaux_r, mgtavcc: {
        "POWERED_DOWN" : 
            PowerState({
                clk: [(0, 0), (3300, 3300), (0, 0)],
                vcc : [(0, 0)], 
                io : [(0, 0)],
                aux : [(0, 0)],
                vcco : [(0, 0)],
                vadj : [(0, 0)],
                vcc_2v5_ddr13 : [(0, 0)],
                vcc_2v5_ddr24 : [(0, 0)],
                vcc_ddr13 : [(0, 0)],
                vcc_ddr24 : [(0, 0)],
                vtt_ddr13 : [(0, 0)],
                vtt_ddr24 : [(0, 0)],
                vtt : [(0, 0)], 
                mgtaux_l : [(0, 0)], 
                mgtaux_r : [(0, 0)], 
                mgtavcc : [(0, 0)],
                ok : [{0}]
            }, {
                "POWERED_ON" : [
                    ({mgtaux_l : [(0, 0)], mgtaux_r : [(0, 0)]}, ""),
                    ({vtt : [(0, 0)]}, ""),
                    ({mgtavcc : [(0, 0)]}, ""),
                    ({vcco: [(0, 0)], vcc_2v5_ddr13 : [(0, 0)], vcc_2v5_ddr24 : [(0, 0)], vcc_ddr13 : [(0, 0)], vcc_ddr24 : [(0, 0)], vtt_ddr13 : [(0, 0)], vtt_ddr24 : [(0, 0)], vadj: [(0, 0)]}, ""),
                    ({aux : [(0, 0)]}, ""),
                    ({io : [(0, 0)]}, ""),
                    ({vcc : [(0, 0)]}, ""),
                ],
                "POWERED_DOWN" : []
            }),
        "POWERED_ON" : 
            PowerState({
                clk: [(0, 0), (3300, 3300), (50, 50)],
                vcc : [(873, 927)],
                io : [(873, 927)],
                aux : [(1746, 1854)],
                vcco : [(1746, 1854)],
                vadj : [(1746, 1854)],
                vcc_2v5_ddr13 : [(2400, 2600)],
                vcc_2v5_ddr24 : [(2400, 2600)],
                vcc_ddr13 : [(1140, 3400)],
                vcc_ddr24 : [(1140, 3400)],
                vtt_ddr13 : [(550, 1700)],
                vtt_ddr24 : [(550, 1700)],
                vtt : [(1164, 1236)],
                mgtaux_l : [(1746, 1854)],
                mgtaux_r : [(1746, 1854)],
                mgtavcc : [(873, 927)],
                ok : [{1}]
            }, {
                "POWERED_DOWN" : [
                    ({clk: [(0, 0), (3300, 3300), (50, 50)]}, ""),
                    ({vcc : [(873, 927)]}, ""),
                    ({io : [(873, 927)]}, ""),
                    ({aux : [(1746, 1854)]}, ""),
                    ({vcco : [(1746, 1854)], vcc_2v5_ddr13 : [(2400, 2600)], vcc_2v5_ddr24 : [(2400, 2600)], vcc_ddr13 : [(1140, 3400)], vcc_ddr24 : [(1140, 3400)], vtt_ddr13 : [(550, 1700)], vtt_ddr24 : [(550, 1700)], vadj: [(1746, 1845)]}, ""),
                    ({mgtavcc : [(873, 927)]}, ""),
                    ({vtt : [(1164, 1236)]}, ""),
                    ({mgtaux_l : [(1746, 1854)], mgtaux_r : [(1746, 1854)]}, ""),
                    ({ok: [{1}]}, "")
                ],
                "POWERED_ON" : []}
            )}, ["CLK", "CLK_OK", "VCCINT", "VCCINT_IO", "VCCAUX", "VCCO_1V8", "VADJ_1V8", "VCCO_2V5_DDR13", "VCCO_2V5_DDR24", "VCCO_VCC_DDR13", "VCCO_VCC_DDR24", "VCCO_VTT_DDR13", "VCCO_VTT_DDR24", "MGTAVTT", "MGTVCCAUX_L", "MGTVCCAUX_R", "MGTAVCC"])
            
            
    def __init__(self, name, bus_addr):
        super(FPGA, self).__init__(name, bus_addr,  "POWERED_DOWN", FPGA)


#EVAL 3 version of the FPGA, comments indicate changes
class FPGA_EVAL3(Stateful_Node):
    CLK = Input([(0, 0), (3300, 3300), (0, 50)], "clock")
    CLK_OK = Input([{0, 1}], "logical")
    VCCO_2V5_DDR24 = Input([(0, 3400)], "power")
    VCCO_2V5_DDR13 = Input([(0, 3400)], "power")
    VCCO_VCC_DDR24 = Input([(0, 3400)], "power")
    VCCO_VTT_DDR13 = Input([(0, 2000)], "power") #replace VREF
    VCCO_VTT_DDR24 = Input([(0, 2000)], "power")
    VCCO_VCC_DDR13 = Input([(0, 3400)], "power")
    VADJ_1V8 = Input([(0, 2000)], "power") #not found in fpga boot sequ; filled in like VCCO_VCC_DDR voltages
    MGTVCCAUX_L = Input([(0, 1900)], "power")
    MGTVCCAUX_R = Input([(0, 1900)], "power")
    VCCO_1V8 = Input([(0, 2000)], "power") #this is sys_1v8....
    VCCINT = Input([(0, 1000)], "power")
    MGTAVCC = Input([(0, 1000)], "power")
    MGTAVTT = Input([(0, 1300)], "power")
    VCCINT_IO = Input([(0, 1000)], "power")
    VCCAUX = Input([(0, 2000)], "power")
    

    states = (lambda clk, ok, vcc, io, aux, vcco, vadj, vcc_2v5_ddr13, vcc_2v5_ddr24, vcc_ddr13, vcc_ddr24, vtt_ddr13, vtt_ddr24, vtt, mgtaux_l, mgtaux_r, mgtavcc: {
        "POWERED_DOWN" : 
            PowerState({
                clk: [(0, 0), (3300, 3300), (0, 0)],
                vcc : [(0, 0)], 
                io : [(0, 0)],
                aux : [(0, 0)],
                vcco : [(0, 0)],
                vadj : [(0, 0)],
                vcc_2v5_ddr13 : [(0, 0)],
                vcc_2v5_ddr24 : [(0, 0)],
                vcc_ddr13 : [(0, 0)],
                vcc_ddr24 : [(0, 0)],
                vtt_ddr13 : [(0, 0)],
                vtt_ddr24 : [(0, 0)],
                vtt : [(0, 0)], 
                mgtaux_l : [(0, 0)], 
                mgtaux_r : [(0, 0)], 
                mgtavcc : [(0, 0)],
                ok : [{0}]
            }, {
                "POWERED_ON" : [
                    ({mgtaux_l : [(0, 0)], mgtaux_r : [(0, 0)]}, ""),
                    ({vtt : [(0, 0)]}, ""),
                    ({mgtavcc : [(0, 0)]}, ""),
                    ({vcco: [(0, 0)], vcc_2v5_ddr13 : [(0, 0)], vcc_2v5_ddr24 : [(0, 0)], vcc_ddr13 : [(0, 0)], vcc_ddr24 : [(0, 0)], vtt_ddr13 : [(0, 0)], vtt_ddr24 : [(0, 0)], vadj: [(0, 0)]}, ""),
                    ({aux : [(0, 0)]}, ""),
                    ({io : [(0, 0)]}, ""),
                    ({vcc : [(0, 0)]}, ""),
                ],
                "POWERED_DOWN" : []
            }),
        "POWERED_ON" : 
            PowerState({
                clk: [(0, 0), (3300, 3300), (50, 50)],
                vcc : [(873, 927)],
                io : [(873, 927)],
                aux : [(1746, 1854)],
                vcco : [(1746, 1854)],
                vadj : [(1746, 1854)],
                vcc_2v5_ddr13 : [(2400, 2600)],
                vcc_2v5_ddr24 : [(2400, 2600)],
                ##### REGULAR VALUES: #######
                #vcc_ddr13 : [(1140, 3400)],
                #vcc_ddr24 : [(1140, 3400)],
                ##### VALUES FOR EVAL 3: #####
                vcc_ddr13 : [(1200, 1200)],
                vcc_ddr24 : [(1200, 1200)],
                #############################
                vtt_ddr13 : [(550, 1700)],
                vtt_ddr24 : [(550, 1700)],
                vtt : [(1164, 1236)],
                mgtaux_l : [(1746, 1854)],
                mgtaux_r : [(1746, 1854)],
                mgtavcc : [(873, 927)],
                ok : [{1}]
            }, {
                "POWERED_DOWN" : [
                    ({clk: [(0, 0), (3300, 3300), (50, 50)]}, ""),
                    ({vcc : [(873, 927)]}, ""),
                    ({io : [(873, 927)]}, ""),
                    ({aux : [(1746, 1854)]}, ""),
                    ##### REGULAR TRANSITION STEP ######
                    #({vcco : [(1746, 1854)], vcc_2v5_ddr13 : [(2400, 2600)], vcc_2v5_ddr24 : [(2400, 2600)], vcc_ddr13 : [(1140, 3400)], vcc_ddr24 : [(1140, 3400)], vtt_ddr13 : [(550, 1700)], vtt_ddr24 : [(550, 1700)], vadj: [(1746, 1845)]}, ""),
                    ##### FOR EVAL 3: ###################
                    ({vcco : [(1746, 1854)], vcc_2v5_ddr13 : [(2400, 2600)], vcc_2v5_ddr24 : [(2400, 2600)], vcc_ddr13 : [(1200, 1200)], vcc_ddr24 : [(1200, 1200)], vtt_ddr13 : [(550, 1700)], vtt_ddr24 : [(550, 1700)], vadj: [(1746, 1845)]}, ""),
                    #####################################
                    ({mgtavcc : [(873, 927)]}, ""),
                    ({vtt : [(1164, 1236)]}, ""),
                    ({mgtaux_l : [(1746, 1854)], mgtaux_r : [(1746, 1854)]}, ""),
                    ({ok: [{1}]}, "")
                ],
                "POWERED_ON" : []}
            )}, ["CLK", "CLK_OK", "VCCINT", "VCCINT_IO", "VCCAUX", "VCCO_1V8", "VADJ_1V8", "VCCO_2V5_DDR13", "VCCO_2V5_DDR24", "VCCO_VCC_DDR13", "VCCO_VCC_DDR24", "VCCO_VTT_DDR13", "VCCO_VTT_DDR24", "MGTAVTT", "MGTVCCAUX_L", "MGTVCCAUX_R", "MGTAVCC"])
            
            
    def __init__(self, name, bus_addr):
        super(FPGA_EVAL3, self).__init__(name, bus_addr,  "POWERED_DOWN", FPGA_EVAL3)
    

class ThunderX(Stateful_Node):
    PLL_DC_OK = Input([{0, 1}], "logical")
    CHIP_RESET_L = Input([{0, 1}], "logical")
    PLL_REF_CLK = Input([(0, 0), (3300, 3300), (0, 50)], "clock")
    VDD = Input([(0, 1210)], "power")
    VDD_09 = Input([(0, 945)], "power")
    VDD_15 = Input([(0, 1650)], "power")
    VDD_DDR13 = Input([(0, 1650)], "power")
    VDD_2V5_DDR13 = Input([(0, 3300)], "power")

    #actually, the CPU names its ddr bank voltage DDR02 (not 24),
    #but I adjusted it to match the schematics, so I know which supplies to connect.. :')
    VDD_DDR24 = Input([(0, 1650)], "power")
    VDD_2V5_DDR24 = Input([(0, 3300)], "power")
    VTT_DDR24 = Input([(0, 1400)], "power")
    VTT_DDR13 = Input([(0, 1400)], "power")
    VDD_IO33 = Input([(0, 3600)], "power")


    states = (lambda ok, rst, clk, vdd, vdd09, vdd15, ddr24, ddr24_2v5, ddr13, ddr13_2v5, vttddr24, vttddr13, io33 : { #pll_vdd, pll_ddr2, pll_ddr13, sys_pll_ddr : {
        "POWERED_DOWN" : 
            PowerState({
                ok : [{0}],
                rst : [{0}],
                clk : [(0, 0), (3300, 3300), (0, 0)],
                vdd : [(0, 0)], 
                vdd09 : [(0, 0)],
                vdd15 : [(0, 0)], 
                ddr24 : [(0, 0)], 
                ddr24_2v5 : [(0, 0)],
                ddr13 : [(0, 0)],
                ddr13_2v5 : [(0, 0)],
                vttddr24 : [(0, 0)], 
                vttddr13 : [(0, 0)], 
                io33 : [(0, 0)] 
            }, {
                "POWERED_ON" : [
                    ({ok : [{0}]}, "")
                ],
                "POWERED_DOWN" : []
            }
            ),
        "POWERED_ON" :
            PowerState({
                ok : [{1}],
                rst : [{1}],
                clk : [(0, 0), (3300, 3300), (50, 50)],
                vdd : [(940, 980)], 
                vdd09 : [(870, 930)],
                vdd15 : [(1450, 1550)], 
                ddr13 : [(1425, 1575)],
                ddr24: [(1425, 1575)],
                ddr24_2v5 : [(2400, 2600)], #not imposed by the cpu, but the connected DIMM SPD needs 2.5 V
                ddr13_2v5 : [(2400, 2600)],
                vttddr24 : [(700, 800)],
                vttddr13 : [(700, 800)],
                io33 : [(3140, 3460)],

            }, {
                "POWERED_DOWN": [
                    ({clk: [(0, 0), (3300, 3300), (50, 50)], io33 : [(3140, 3460)]}, "wait for %s to stabilize" %(io33)),
                    ({vdd : [(940, 980)]}, ""),
                    ({vdd09 : [(870, 930)], vdd15 : [(1450, 1550)]}, ""),
                    ({ddr24 : [(1425, 1575)], ddr24_2v5 : [(2400, 2600)], ddr13 : [(1425, 1575)], ddr13_2v5 : [(2400, 2600)], vttddr24 : [(700, 800)], vttddr13 : [(700, 800)]}, "%s should have stabilized by now" %vdd),
                    ({ok : [{1}]}, "must have written pll_mul and sys_pll_mul beforehand"),
                    ({rst : [{1}]}, "")

                ], 
                "POWERED_ON" : [] })
    }, ["PLL_DC_OK", "CHIP_RESET_L", "PLL_REF_CLK", "VDD", "VDD_09", "VDD_15", "VDD_DDR24", "VDD_2V5_DDR24", "VDD_DDR13", "VDD_2V5_DDR13", "VTT_DDR24", "VTT_DDR13", "VDD_IO33"]) #"VDD_IO25", "VDD_IO33"])

    def __init__(self, name, bus_addr):
        super(ThunderX, self).__init__(name, bus_addr, "POWERED_DOWN", ThunderX)


#EVAL 3 version of the THUNDERX: Comments indicate changes
class ThunderX_EVAL3(Stateful_Node): 
    PLL_DC_OK = Input([{0, 1}], "logical")
    CHIP_RESET_L = Input([{0, 1}], "logical")
    PLL_REF_CLK = Input([(0, 0), (3300, 3300), (0, 50)], "clock")
    VDD = Input([(0, 1210)], "power")
    VDD_09 = Input([(0, 945)], "power")
    VDD_15 = Input([(0, 1650)], "power")
    VDD_DDR13 = Input([(0, 1650)], "power")
    VDD_2V5_DDR13 = Input([(0, 3300)], "power")

    #actually, the CPU names its ddr bank voltage DDR02 (not 24),
    #but I adjusted it to match the schematics, so I know which supplies to connect.. :')
    VDD_DDR24 = Input([(0, 1650)], "power")
    VDD_2V5_DDR24 = Input([(0, 3300)], "power")
    VTT_DDR24 = Input([(0, 1400)], "power")
    VTT_DDR13 = Input([(0, 1400)], "power")
    VDD_IO33 = Input([(0, 3600)], "power")


    states = (lambda ok, rst, clk, vdd, vdd09, vdd15, ddr24, ddr24_2v5, ddr13, ddr13_2v5, vttddr24, vttddr13, io33 : { #pll_vdd, pll_ddr2, pll_ddr13, sys_pll_ddr : {
        "POWERED_DOWN" : 
            PowerState({
                ok : [{0}],
                rst : [{0}],
                clk : [(0, 0), (3300, 3300), (0, 0)],
                vdd : [(0, 0)], 
                vdd09 : [(0, 0)],
                vdd15 : [(0, 0)], 
                ddr24 : [(0, 0)], 
                ddr24_2v5 : [(0, 0)],
                ddr13 : [(0, 0)],
                ddr13_2v5 : [(0, 0)],
                vttddr24 : [(0, 0)], 
                vttddr13 : [(0, 0)], 
                io33 : [(0, 0)] 
            }, {
                "POWERED_ON" : [
                    ({ok : [{0}]}, "")
                ],
                "POWERED_DOWN" : []
            }
            ),
        "POWERED_ON" :
            PowerState({
                ok : [{1}],
                rst : [{1}],
                clk : [(0, 0), (3300, 3300), (50, 50)],
                vdd : [(940, 980)], 
                vdd09 : [(870, 930)],
                vdd15 : [(1450, 1550)], 
                ####### REGULAR VALUES #########
                #ddr13 : [(1425, 1575)],
                #ddr24: [(1425, 1575)],
                ####### FOR EVAL 3 ###########
                ddr24: [(1200, 1200)],
                ddr13: [(1200, 1200)],
                #################################
                ddr24_2v5 : [(2400, 2600)], #not imposed by the cpu, but the connected DIMM SPD needs 2.5 V
                ddr13_2v5 : [(2400, 2600)],
                vttddr24 : [(570, 630)],
                vttddr13 : [(570, 630)],
                io33 : [(3140, 3460)],

            }, {
                "POWERED_DOWN": [
                    ({clk: [(0, 0), (3300, 3300), (50, 50)], io33 : [(3140, 3460)]}, "wait for %s to stabilize" %(io33)),
                    ({vdd : [(940, 980)]}, ""),
                    ({vdd09 : [(870, 930)], vdd15 : [(1450, 1550)]}, ""),
                    #### REGULAR TRANSITION STEP #########
                    #({ddr24 : [(1425, 1575)], ddr24_2v5 : [(2400, 2600)], ddr13 : [(1425, 1575)], ddr13_2v5 : [(2400, 2600)], vttddr24 : [(700, 800)], vttddr13 : [(700, 800)]}, "%s should have stabilized by now" %vdd),
                    #### FOR EVAL 3 ######################
                    ({ddr24 : [(1200, 1200)], ddr24_2v5 : [(2400, 2600)], ddr13 : [(1200, 1200)], ddr13_2v5 : [(2400, 2600)], vttddr24 : [(570, 630)], vttddr13 : [(570, 630)]}, "%s should have stabilized by now" %vdd),
                    ######################################
                    ({ok : [{1}]}, "must have written pll_mul and sys_pll_mul beforehand"),
                    ({rst : [{1}]}, "")

                ], 
                "POWERED_ON" : [] })
    }, ["PLL_DC_OK", "CHIP_RESET_L", "PLL_REF_CLK", "VDD", "VDD_09", "VDD_15", "VDD_DDR24", "VDD_2V5_DDR24", "VDD_DDR13", "VDD_2V5_DDR13", "VTT_DDR24", "VTT_DDR13", "VDD_IO33"]) #"VDD_IO25", "VDD_IO33"])

    def __init__(self, name, bus_addr):
        super(ThunderX_EVAL3, self).__init__(name, bus_addr, "POWERED_DOWN", ThunderX_EVAL3)


class Bus(Node):
    BUS = Output([{0, 1}],
                [
                
                Constraint([{1}], lambda node, inputs: node.construct_req(inputs), lambda node, name, inputs: node.construct_dependency(name, node.construct_req(inputs))),
                Constraint([{0}], lambda node, inputs: {}, lambda node, name, inputs: node.construct_dependency(name, node.construct_req_off(inputs)))
                ], "bus")

    def __init__(self, name, bus_addr):
        super(Bus, self).__init__(name, bus_addr,  Bus)


    def construct_req(self, inputs):
        req = {}
        for node, _ in inputs:
            unite_dict(req, node.bus_req())
        print(req)
        return req

    def construct_req_off(self, inputs):
        req = {}
        for node, _ in inputs:
            node_req = node.bus_req_off()
            for wire, state in node_req.items():
                if not wire in req:
                    req[wire] = state
                else:
                    req[wire] = state_union(state, req[wire])
        print(req)
        return req



    def construct_dependency(self, name, req):
        return (SET.Implicit, [set(), set(), set(), set()], lambda states, req = req: {name : set(filter(lambda x: not empty_intersection(x, req, states), req.keys()))})




                              



class MAX20751(Node):
    implicit_on = {"VR_ON": [{1}], "VDD33":[(2970, 3630)], "VDDH":[(8500, 14000)]}
    implicit_off = {"VR_ON": [{0}], "VDD33": [0, 2800], "VDDH": [(0, 8499)]}
    VDD33 = Input([(0, 4000)], "power")
    BUS = Input([{0, 1}], "bus")
    VDDH = Input([(0, 23000)], "power") #slave input power
    VR_ON = Input([{0, 1}], "logical")
    V_OUT = lambda default : Output([(0, 1520)], 
                                    [Constraint([], {"VR_ON": [{1}], "VDD33":[(2970, 3630)], "VDDH":[(8500, 14000)]}, partial(Constraint.implicit, "V_OUT", MAX20751.implicit_on), state_update= Constraint.default_state),
                                    Constraint([(500, 1520)], {"VR_ON": [{1}], "VDD33":[(2970, 3630)], "VDDH":[(8500, 14000)], "BUS" : [{1}]}, {}, dependency_update = (Constraint.is_default, [partial(Constraint.explicit, "V_OUT", {"VDD33", "VDDH", "BUS"}, {"VR_ON"}, after_set = {"VR_ON"}),  partial(Constraint.explicit, "V_OUT", {"VDD33", "VDDH", "BUS", "VR_ON"}, set())])),
                                    Constraint([(0, 0)], {"VR_ON": [{0}], "VDD33":[(0, 3630)], "VDDH":[(0, 14000)]}, partial(Constraint.implicit, "V_OUT", MAX20751.implicit_off)),
                                    ], "power", Wire.voltage_set)

    
    
    def __init__(self, name, bus_addr, default, device):
        self.device = device
        self.default = default
        self.is_default = False
        self.current = [(default, default)]
        self.V_OUT = MAX20751.V_OUT(default)
        super(MAX20751, self).__init__(name, bus_addr, MAX20751)

    def bus_req(self):
        return {} 

    def bus_req_off(self):
        return {}


    def update(self, states):
        try:
            intersect(states[self.V_OUT.name], [(500, 1520)])
            self.current = states[self.V_OUT.name]
            self.is_default = True
            return
        except State_Space_Error:
            self.is_default = False
        try:
            intersect(states[self.VDD33.name], [(0, 2800)])
            self.current = [(self.default, self.default)]
            return
        except State_Space_Error:
            pass
        try:
            intersect(states[self.VDDH.name], [(8500, 14000)])
            self.current = [(self.default, self.default)]
            return
        except State_Space_Error:
            pass


class Oscillator(Node):
    VDD = Input([(0, 3600)], "power")
    CLK = Output([(0, 0), (3300, 3300), (0, 50)], [
        Constraint([(0, 0), (3300, 3300), (50, 50)], {"VDD": [(2600, 3600)]}, partial(Constraint.implicit, "CLK", {"VDD": [(2600, 3600)]})),
        Constraint([(0, 0), (3300, 3300), (0, 0)], {"VDD": [(0, 2599)]}, partial(Constraint.implicit, "CLK", {"VDD": [(0, 2599)]}))], "clock", Wire.clock_config)

    def __init__(self, name, bus_addr):
        super(Oscillator, self).__init__(name, bus_addr, Oscillator)

class SI5395(Node):
    implicit_on = {"VDD": [(2600, 3600)], "CLK_IN": [(0, 0), (3300, 3300), (50, 50)]}
    implicit_off = {"VDD": [(0, 2599)], "CLK_IN": [(0, 0), (3300, 3300), (0, 0)]}
    VDD = Input([(0, 3600)], "power")
    CLK_IN = Input([(0, 0), (3300, 3300), (0, 50)], "clock")
    CLK = Output([(0, 0), (3300, 3300), (0, 50)], [
        Constraint([(0, 0), (3300, 3300), (50, 50)], {"VDD": [(2600, 3600)], "CLK_IN": [(0, 0), (3300, 3300), (50, 50)]}, partial(Constraint.explicit, "CLK", {"VDD", "CLK_IN"}, set())),
        Constraint([(0, 0), (3300, 3300), (0, 0)], {"VDD": [(2600, 3600)], "CLK_IN": [(0, 0), (3300, 3300), (50, 50)]}, partial(Constraint.implicit, "CLK", "implicit_on"), dependency_update= (Constraint.is_configured, [partial(Constraint.implicit, "CLK", "implicit_on"),  partial(Constraint.explicit, "CLK", {}, set())])),
        Constraint([(0, 0), (3300, 3300), (0, 0)], {"VDD": [(0, 2599)]}, partial(Constraint.implicit, "CLK", "implicit_off")),
        Constraint([(0, 0), (3300, 3300), (0, 0)], {"CLK_IN": [(0, 0), (3300, 3300), (0, 0)]}, partial(Constraint.implicit, "CLK", "implicit_off"))], "clock", Wire.clock_config)

    def __init__(self, name, bus_addr,  device):
        self.device = device
        self.configured = False
        super(SI5395, self).__init__(name, bus_addr, SI5395)
    
    def update(self, states):
        try:
            intersect(states[self.VDD.name], [(2600, 3600)])
        except State_Space_Error:
            self.configured = False

    def configure(self):
        if self.configured:
            return []
        else:
            self.configured = True
            return [
                "init_device('%s', False)" % (self.device)
            ]



class Clock(Node):
    CLK = Output([(0, 3300), (0, 60)], [([(0, 3300), (0, 60)], {}, [], lambda node: node.indep("CLK"))], "clock", Wire.clock_config)

    def __init__(self, name, bus_addr):
        super(Clock, self).__init__(name, bus_addr,  Clock)

class PowerConsumer(Node):
    node_string = "<V_IN> V_IN"
    V_IN = Input([(0, 12000)], "power")

    def __init__(self, name, bus_addr):
        super(PowerConsumer, self).__init__(name, bus_addr, PowerConsumer)


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
        super(CPU2, self).__init__(name, bus_addr,  "POWERED_DOWN", CPU2)

    
class BMC(Node):
    B_CLOCK_FLOL = Output([{0, 1}], [Constraint([{0, 1}], {}, partial(Constraint.explicit, "B_CLOCK_FLOL", set(), set()))], "logical", Wire.fpga_clk_ok)
    B_PSUP_ON = Output([{0, 1}], [Constraint([{0, 1}], {}, partial(Constraint.explicit, "B_PSUP_ON", set(), set()))], "logical", Wire.gpio_set)
    C_RESET_N = Output([{0, 1}], [Constraint([{0, 1}], {}, partial(Constraint.explicit, "C_RESET_N", set(), set()))], "logical", Wire.gpio_set)
    C_PLL_DC_OK = Output([{0, 1}], [Constraint([{0, 1}], {}, partial(Constraint.explicit, "C_PLL_DC_OK", set(), set()))], "logical", Wire.cpu_clk_ok)
    B_FDV_1V8  = Output([{0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}], [
        Constraint([{0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}], {}, partial(Constraint.explicit, "B_FDV_1V8", set(), set()))], "logical", Wire.vid_set)
    B_CDV_1V8  = Output([{0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}], [
        Constraint([{0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}, {0, 1}], {}, partial(Constraint.explicit, "B_CDV_1V8", set(), set()))], "logical", Wire.vid_set)
    
    
    def __init__(self, name, bus_addr):
        super(BMC, self).__init__(name, bus_addr,  BMC)
        self.configured = False

    def configure(self):
        if self.configured:
            return []
        else:
            self.configured = True
            return [
                "init_device('isl6334d_ddr_v', False)"
            ]



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


class PSU(Node):
    EN = Input([{0, 1}], "logical")
    OUT = Output([(0, 12000)], [
        Constraint([(12000, 12000)], {"EN" : [{1}]}, partial(Constraint.implicit, "OUT", {"EN": [{1}]})),
        Constraint([(0, 0)], {"EN": [{0}]}, partial(Constraint.implicit, "OUT", {"EN": [{0}]}))], "power")

    def __init__(self, name, bus_addr):
        super(PSU, self).__init__(name, bus_addr, PSU)


class Main_PSU(Node):
    EN = Input([{0, 1}], "logical")
    V33_PSU = Output([(0, 3300)], [
        Constraint([(3300, 3300)], {"EN": [{1}]}, partial(Constraint.implicit, "V33_PSU", {"EN": [{1}]})),
        Constraint([(0, 0)], {"EN": [{0}]}, partial(Constraint.implicit, "V33_PSU", {"EN": [{0}]}))], "power")
    V12_PSU = Output([(0, 12000)], [
        Constraint([(12000, 12000)], {"EN" : [{1}]}, partial(Constraint.implicit, "V12_PSU", {"EN" : [{1}]})),
        Constraint([(0, 0)], {"EN": [{0}]}, partial(Constraint.implicit, "V12_PSU", {"EN": [{0}]}))], "power")


    V5SB_PSU = Output([(5000, 5000)], [Constraint([(5000, 5000)], {}, partial(Constraint.implicit, "V5SB_PSU", {}))], "power")
    BMC_VCC_3V3 = Output([(3300, 3300)], [Constraint([(3300, 3300)], {}, partial(Constraint.implicit, "BMC_VCC_3V3", {}))], "power")
    V5_PSU = Output([(0, 5000)], [
        Constraint([(5000, 5000)], {"EN": [{1}]}, partial(Constraint.implicit, "V5_PSU", {"EN" : [{1}]})),
        Constraint([(0, 0)], {"EN": [{0}]}, partial(Constraint.implicit, "V5_PSU", {"EN": [{0}]}))], "power")
    
    def __init__(self, name, bus_addr):
        super(Main_PSU, self).__init__(name, bus_addr,  Main_PSU)
    


class PowerSupply(Node):
    OUT0 = Output([(0, 12000)], [([(0, 12000)], {}, [], lambda node: node.indep("OUT0"))], "power")
    OUT1 = Output([(0, 12000)], [([(0, 12000)], {}, [], lambda node: node.indep("OUT1"))], "power")
    OUT2 = Output([(0, 12000)], [([(0, 12000)], {}, [], lambda node: node.indep("OUT2"))], "power")

    def __init__(self, name, bus_addr):
        super(PowerSupply, self).__init__(name, bus_addr, PowerSupply)




class ISPPAC(Node):
    implicit_off = {"VCC": [(0, 2600)], "VCC_IN": [(0, 2000)]}
    VMON1_ATT = Input([(0, 13900)], "monitor", lambda node, name: node.isppac_monitor("VMON1_ATT", name, 0.4125))
    VMON2_ATT = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON2_ATT", name))
    VMON3_ATT = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON3_ATT", name))
    VMON4 = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON4", name))
    VMON4_ATT = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON4_ATT", name))
    VMON5 = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON5", name))
    VMON5_ATT = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON5_ATT", name))
    VMON6 = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON6", name))
    VMON7 = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON7", name))
    VMON7_ATT = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON7_ATT", name))
    VMON8 = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON8", name))
    VMON8_ATT = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON8_ATT", name))
    VMON9 = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON9", name))
    VMON10 = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON10", name))
    VMON11 = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON11", name))
    VMON11_ATT = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON11_ATT", name))
    VMON12 = Input([(0, 5734)], "monitor", lambda node, name: node.isppac_monitor("VMON12", name))
    VCC_IN = Input([(0, 6000)], "power", lambda node, name: node.isppac_monitor("VCCINP", name))
    VCC = Input([(0, 4500)], "power", lambda node, name: node.isppac_monitor("VCCA", name))

    def __init__(self, name, bus_addr, device):
        self.device = device
        for i in range(0, 20):
            self.generate_output(i)
        super(ISPPAC, self).__init__(name, bus_addr, ISPPAC)
        self.configured = False

    def generate_output(self, number):
        name = "OUT" + str(number)
        output = Output([{0, 1}],
                  [Constraint([{1, 0}], {"VCC": [(2800, 3960)], "VCC_IN": [(2250, 5500)]}, partial(Constraint.explicit, name, {"VCC", "VCC_IN"}, set())),
                   Constraint([{0}], {"VCC": [(0, 2600)], "VCC_IN": [(0, 6000)]}, partial(Constraint.implicit, name, "implicit_off")),
                   Constraint([{0}], {"VCC": [(0, 4500)], "VCC_IN": [(0, 2000)]}, partial(Constraint.implicit, name, "implicit_off"))], "logical", Wire.pin_set)
        setattr(self, name, output)

    def isppac_monitor(self, pinname, wire_name, multiplier = 1):
        def fun(value, _, node=self, wire_name=wire_name, pinname=pinname, multiplier=multiplier):
            commands = node.configure()
            if list(value[0])[0] == 0:
                commands.append("wait_for_voltage('%s', v_min=0, v_max=0.08, device='%s', monitor='%s')" % (
                    wire_name,
                    node.device,
                    pinname
                ))
            else:
                commands.append("wait_for_voltage('%s', v_min=%.3f, v_max=%.3f, device='%s', monitor='%s')" % (
                    wire_name,
                    0.00095 * list(value[0])[0] * multiplier,
                    0.00105 * list(value[0])[0] * multiplier,
                    node.device,
                    pinname
                ))
            return (True, "\n".join(commands))
        return fun

    def configure(self):
        if self.configured:
            return []
        else:
            self.configured = True
            return [
                "init_device('%s', False)" % (self.device)
            ]


#EVAL 3 version of the Enzian nodes, only changes classes of ThunderX and FPGA to EVAL 3 versions
enzian_nodes_EVAL3 = [
    
    ("power_bus", 0x0, Bus, []),
    ("psu_cpu0", 0x0, PSU, []), 
    ("psu_cpu1", 0x0, PSU, []),
    ("main_psu", 0x0, Main_PSU, []),
    ("U20", 0x60, ISPPAC, ["pac_cpu"]), #cpu ISPPAC
    ("U35", 0x61, ISPPAC, ["pac_fpga"]), #fpga ISPPAC
    ("U44", 0x40, INA226, ["ina226_ddr_fpga_24"]), 
    ("U48", 0x41, INA226, ["ina226_ddr_fpga_13"]),
    ("U27", 0x44, INA226, ["ina226_ddr_cpu_13"]),
    ("U31", 0x45, INA226, ["ina226_ddr_cpu_24"]),   
    

    #TODO: add real names of MAX15301s
    ("IC12", 0x11, MAX15301, [1800, "max15301_vcc1v8_fpga"]), #VCCIV8_FPGA p 92
    ("IC10", 0x1B, MAX15301, [3300, "max15301_util_3v3"]), #UTIL_3V3 p.90
    ("IC4", 0x10, MAX15301, [1500, "max15301_15_vdd_oct"]), #1V5_VDD_OCT p.70
    ("IC11", 0x12, MAX15301, [1800, "max15301_vadj_1v8"]), #VADJ_1V8 p.91
    ("IC13", 0x15, MAX15301, [900, "max15301_vccintio_bram_fpga"]), #VCCINTIO_FPGA p 99
    ("U34", 0x0, IR, [4500, "ir3581", "ir3581_loop_vdd_core", "ir3581_loop_0v9_vdd_oct", 0x60, 0x62]), #VDD_CORE, VDD_OCT p 77
    ("U26", 0x0, ISL, []), #VDD_DDRCPU13 p 73
    ("U30", 0x0, ISL, []), #VDD_DDRCPU24 p 75
    ("U37", 0x72, MAX20751, [900, "max20751_mgtavcc_fpga"]), #MGTACC_FPGA p 85
    ("U41", 0x73, MAX20751, [1200,"max20751_mgtavtt_fpga"]), #MGTAVTT_FPGA p 87
    ("U51", 0x70, MAX20751, [900, "max20751_vccint_fpga"]), #VCCINT_FPGA p 97
    ("U43", 0x0, ISL, []), #VDD_DDRFPGA13 p 93
    ("U47", 0x0, ISL, []), #DD_DDRFPGA24 p 95
    ("IC5", 0x0, MAX8869, [1800]), #MGTVCCAUX_L, p 88
    ("IC6", 0x0, MAX8869, [1800]), #MGTVCCAUX_R, p 88
    ("IC7", 0x0, MAX15053, [1800]), #SYS_1V8, p 89
    ("IC8", 0x0, MAX15053, [2500]), #SYS_2V5_13
    ("IC9", 0x0, MAX15053, [2500]), #SYS_2V5_24
    ("IC15", 0x0, MAX15053, [2500]), #2V5_CPU13 p 71
    ("IC16", 0x0, MAX15053, [2500]),  #2V5_CPU24 p 71
    ("fpga", 0x0, FPGA_EVAL3, []),
    ("cpu", 0x0, ThunderX_EVAL3, []),
    ("bmc", 0x0, BMC, []),
    ("U24", 0x0, NCP, []),
    ("U25", 0x0, NCP, []),
    ("U39", 0x0, NCP, []), 
    ("U40", 0x0, NCP, []),
    ("U57", 0x0, SI5395, ["clk_main"]),
    ("U11", 0x0, SI5395, ["clk_cpu"]),
    ("U16", 0x0, SI5395, ["clk_fpga"]),
    ("oscillator", 0x0, Oscillator, []),
    
]






enzian_nodes = [
    
    ("power_bus", 0x0, Bus, []),
    ("psu_cpu0", 0x0, PSU, []), 
    ("psu_cpu1", 0x0, PSU, []),
    ("main_psu", 0x0, Main_PSU, []),
    ("U20", 0x60, ISPPAC, ["pac_cpu"]), #cpu ISPPAC
    ("U35", 0x61, ISPPAC, ["pac_fpga"]), #fpga ISPPAC
    ("U44", 0x40, INA226, ["ina226_ddr_fpga_24"]), 
    ("U48", 0x41, INA226, ["ina226_ddr_fpga_13"]),
    ("U27", 0x44, INA226, ["ina226_ddr_cpu_13"]),
    ("U31", 0x45, INA226, ["ina226_ddr_cpu_24"]),   
    

    #TODO: add real names of MAX15301s
    ("IC12", 0x11, MAX15301, [1800, "max15301_vcc1v8_fpga"]), #VCCIV8_FPGA p 92
    ("IC10", 0x1B, MAX15301, [3300, "max15301_util_3v3"]), #UTIL_3V3 p.90
    ("IC4", 0x10, MAX15301, [1500, "max15301_15_vdd_oct"]), #1V5_VDD_OCT p.70
    ("IC11", 0x12, MAX15301, [1800, "max15301_vadj_1v8"]), #VADJ_1V8 p.91
    ("IC13", 0x15, MAX15301, [900, "max15301_vccintio_bram_fpga"]), #VCCINTIO_FPGA p 99
    ("U34", 0x0, IR, [4500, "ir3581", "ir3581_loop_vdd_core", "ir3581_loop_0v9_vdd_oct", 0x60, 0x62]), #VDD_CORE, VDD_OCT p 77
    ("U26", 0x0, ISL, []), #VDD_DDRCPU13 p 73
    ("U30", 0x0, ISL, []), #VDD_DDRCPU24 p 75
    ("U37", 0x72, MAX20751, [900, "max20751_mgtavcc_fpga"]), #MGTACC_FPGA p 85
    ("U41", 0x73, MAX20751, [1200,"max20751_mgtavtt_fpga"]), #MGTAVTT_FPGA p 87
    ("U51", 0x70, MAX20751, [900, "max20751_vccint_fpga"]), #VCCINT_FPGA p 97
    ("U43", 0x0, ISL, []), #VDD_DDRFPGA13 p 93
    ("U47", 0x0, ISL, []), #DD_DDRFPGA24 p 95
    ("IC5", 0x0, MAX8869, [1800]), #MGTVCCAUX_L, p 88
    ("IC6", 0x0, MAX8869, [1800]), #MGTVCCAUX_R, p 88
    ("IC7", 0x0, MAX15053, [1800]), #SYS_1V8, p 89
    ("IC8", 0x0, MAX15053, [2500]), #SYS_2V5_13
    ("IC9", 0x0, MAX15053, [2500]), #SYS_2V5_24
    ("IC15", 0x0, MAX15053, [2500]), #2V5_CPU13 p 71
    ("IC16", 0x0, MAX15053, [2500]),  #2V5_CPU24 p 71
    ("fpga", 0x0, FPGA, []),
    ("cpu", 0x0, ThunderX, []),
    ("bmc", 0x0, BMC, []),
    ("U24", 0x0, NCP, []),
    ("U25", 0x0, NCP, []),
    ("U39", 0x0, NCP, []), 
    ("U40", 0x0, NCP, []),
    ("U57", 0x0, SI5395, ["clk_main"]),
    ("U11", 0x0, SI5395, ["clk_cpu"]),
    ("U16", 0x0, SI5395, ["clk_fpga"]),
    ("oscillator", 0x0, Oscillator, []),
    
]


enzian_wires = [
    
    ("b_psup_on", "bmc", "B_PSUP_ON", {("psu_cpu0", "EN"), ("psu_cpu1", "EN"), ("main_psu", "EN")}),
    ("3v3_psup", "main_psu", "V33_PSU", {("U20", "VMON3_ATT"), ("U27", "VS"), ("U31", "VS"), ("IC15", "V_IN"), ("IC16", "V_IN"), ("cpu", "VDD_IO33"), ("U34", "VCC"), ("U57", "VDD"), ("U11", "VDD"), ("U16", "VDD"), ("oscillator", "VDD")}),
    #("12v_psup", "main_psu", "V12_PSU", {}), #add bmc
    ("5v_psup", "main_psu", "V5_PSU", {("U35", "VMON2_ATT"), ("U20", "VMON2_ATT"), ("U26", "VCC"), ("U30", "VCC"), ("U43", "VCC"), ("U47", "VCC")}),

    ("5vsb_psup", "main_psu", "V5SB_PSU", {("U20", "VCC_IN"), ("U35", "VCC_IN")}),
    ("bmc_vcc_3v3", "main_psu", "BMC_VCC_3V3", {("U20", "VCC"), ("U35", "VCC")}),


   
    #add 5vsb if added bmc
    ("12v_cpu0_psup", "psu_cpu0", "OUT", {("U20", "VMON1_ATT"), ("IC4", "V_PWR"), ("U26", "EN_VTT"), ("U30", "EN_VTT"), ("U34", "VIN")}),
    ("12v_cpu1_psup", "psu_cpu1", "OUT", {("U35", "VMON1_ATT"), ("U37", "VDDH"), ("U41", "VDDH"), ("IC10", "V_PWR"), ("IC11", "V_PWR"), ("IC12", "V_PWR"), ("U43", "EN_VTT"), ("U47", "EN_VTT"), ("U51", "VDDH"), ("IC13", "V_PWR")}),
    ("en_vcc1v8_fpga", "U35", "OUT15", {("IC12", "EN")}),
    ("vcc1v8_fpga", "IC12", "V_OUT", {("U35", "VMON11_ATT"), ("fpga", "VCCAUX")}),
    ("en_util33", "U35", "OUT6", {("IC10", "EN")}),
    ("util33", "IC10", "V_OUT", {("U35", "VMON3_ATT"), ("U44", "VS"), ("U48", "VS"), ("U37", "VDD33"), ("U41", "VDD33"), ("IC5", "V_IN"), ("IC6", "V_IN"), ("IC7", "V_IN"), ("IC8", "V_IN"), ("IC9", "V_IN"), ("U51", "VDD33")}),
    ("en_mgtavtt_fpga", "U35", "OUT14", {("U41", "VR_ON")}),
    ("mgtavtt_fpga", "U41", "V_OUT", {("fpga", "MGTAVTT")}),
    ("en_mgtavcc_fpga", "U35", "OUT10", {("U37", "VR_ON")}),
    ("mgtavcc_fpga", "U37", "V_OUT", {("U35", "VMON7"), ("fpga", "MGTAVCC")}),
    ("en_vccint_fpga", "U35", "OUT9", {("U51", "VR_ON")}),
    ("vccint_fpga", "U51", "V_OUT", {("U35", "VMON6"), ("fpga", "VCCINT")}),
    ("en_sys_1v8", "U35", "OUT16", {("IC7", "V_EN")}),
    ("sys_1v8", "IC7", "V_OUT", {("U35", "VMON12"), ("fpga", "VCCO_1V8")}), #where to connect at fpga? additional vcco thingy?
    
    
    ("en_sys_2v5_13", "U35", "OUT7", { ("IC8", "V_EN")}),
    ("sys_2v5_13", "IC8", "V_OUT", {("U35", "VMON4_ATT"), ("U39", "VCC"), ("fpga", "VCCO_2V5_DDR13")}), #add NCP nodes
    ("vtt_ddrfpga13", "U39", "VREF", {("fpga", "VCCO_VTT_DDR13")}),

    ("en_sys_2v5_24", "U35", "OUT8", { ("IC9", "V_EN")}),
    ("sys_2v5_24", "IC9", "V_OUT", {("U35", "VMON5_ATT"), ("U40", "VCC"), ("fpga", "VCCO_2V5_DDR24")}), #add NCP nodes
    ("vtt_ddrfpga24", "U40", "VREF", {("fpga", "VCCO_VTT_DDR24")}),

    ("clk_sig", "oscillator", "CLK", {("U57", "CLK_IN")}),
    ("clk_main", "U57", "CLK", {("U11", "CLK_IN"), ("U16", "CLK_IN")}),

    ("clock_flol", "bmc", "B_CLOCK_FLOL", {("fpga", "CLK_OK")}),
    ("fpga_clk", "U16", "CLK", {("fpga", "CLK")}),

    

    ("en_mgtvccaux_l", "U35", "OUT11", {("IC5", "SHDN")}),
    ("en_mgtvccaux_r", "U35", "OUT12", {("IC6", "SHDN")}),
    ("mgtvccaux_l", "IC5", "V_OUT", {("U35", "VMON8"), ("fpga", "MGTVCCAUX_L")}),
    ("mgtvccaux_r", "IC6", "V_OUT", {("U35", "VMON9"), ("fpga", "MGTVCCAUX_R")}),
    ("en_vadj_1v8_fpga", "U35", "OUT17", {("IC11", "EN")}),
    ("vadj_1v8_fpga", "IC11", "V_OUT", {("fpga", "VADJ_1V8")}), 
    ("en_vccintio_bram_fpga", "U35", "OUT13", {("IC13", "EN")}),
    ("vccintio_bram_fpga", "IC13", "V_OUT", {("U35", "VMON10"), ("fpga", "VCCINT_IO")}),
    ("en_vdd_ddrfpga13", "U35", "OUT18", {("U43", "EN_PWR")}),
    ("en_vdd_ddrfpga24", "U35", "OUT19", {("U47", "EN_PWR")}),
    ("vdd_ddrfpga13", "U43", "VOUT", {("U48", "VBUS"), ("fpga", "VCCO_VCC_DDR13"), ("U39", "VRI")}), #vcco
    ("vdd_ddrfpga24", "U47", "VOUT", {("U44", "VBUS"), ("fpga", "VCCO_VCC_DDR24"), ("U40", "VRI")}),

    
    ("b_cdv_1v8", "bmc", "B_CDV_1V8", {("U26", "VID"), ("U30", "VID")}),
    ("b_fdv_1v8", "bmc", "B_FDV_1V8", {("U43", "VID"), ("U47", "VID")}),


    ("c_reset_n", "bmc", "C_RESET_N", {("cpu", "CHIP_RESET_L")}),
    ("pll_dc_ok", "bmc", "C_PLL_DC_OK", {("cpu", "PLL_DC_OK")}),

    ("en_vdd_ddrcpu13", "U20", "OUT11", {("U26", "EN_PWR")}),
    ("en_vdd_ddrcpu24", "U20", "OUT12", {("U30", "EN_PWR")}),
    ("vdd_ddrcpu13", "U26", "VOUT", {("U20", "VMON9"), ("U27", "VBUS"), ("cpu", "VDD_DDR13"), ("U24", "VRI")}),
    ("vdd_ddrcpu24", "U30", "VOUT", {("U20", "VMON10"), ("U31", "VBUS"), ("cpu", "VDD_DDR24"), ("U25", "VRI")}),
    ("vdd_core_en", "U20", "OUT6", {("U34", "EN")}),
    ("vdd_core", "U34", "VOUT", {("U20", "VMON4"), ("cpu", "VDD")}),
    ("vdd_oct_en_l2", "U20", "OUT7", {("U34", "EN_2")}),
    ("0v9_vdd_oct", "U34", "VOUT_2", {("U20", "VMON5"), ("cpu", "VDD_09")}),
    ("en_1v5_vdd_oct", "U20", "OUT8", {("IC4", "EN")}),
    ("1v5_vdd_oct", "IC4", "V_OUT", {("U20", "VMON6"), ("cpu", "VDD_15")}),


    ("en_2v5_cpu13", "U20", "OUT9", {("IC15", "V_EN")}), #to NCP
    ("2v5_cpu13", "IC15", "V_OUT", {("U20", "VMON7_ATT"), ("U24", "VCC"), ("cpu", "VDD_2V5_DDR13")}),
    ("vtt_ddrcpu13", "U24", "VREF", {("U20", "VMON11"), ("cpu", "VTT_DDR13")}),
    
    ("en_2v5_cpu24", "U20", "OUT10", {("IC16", "V_EN")}), #to NCP
    ("2v5_cpu24", "IC16", "V_OUT", {("U20", "VMON8_ATT"), ("U25", "VCC"), ("cpu", "VDD_2V5_DDR24")}),
    ("vtt_ddrcpu24", "U25", "VREF", {("U20", "VMON12"), ("cpu", "VTT_DDR24")}),

    ("pll_ref_clk", "U11", "CLK", {("cpu", "PLL_REF_CLK")}),
    ("bus", "power_bus", "BUS", {("IC10", "BUS"), ("IC12", "BUS"), ("IC13", "BUS"), ("IC4", "BUS"), ("IC11", "BUS"), ("U34", "BUS"), ("U37", "BUS"), ("U41", "BUS"), ("U51", "BUS")}),
    
    
]
