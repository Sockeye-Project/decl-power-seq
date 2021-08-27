
#Manual boot sequence with annotated events (orginal code taken from Enzian gitlab)
def power_up():
    power.device_write("pac_cpu", "reset", True) #establish known state
    power.device_write("pac_fpga", "reset", True) #establish known state
    check_voltage('CPU:BMC_VCC_3V3', lambda: read_pac_adc("pac_cpu", "VCCA"), 3.135, 3.465) #Complete(bmc_vcc_3v3)
    check_voltage('CPU:BMC_VCC_5V', lambda: read_pac_adc("pac_cpu", "VCCINP"), 4.75, 5.25) #Complete(5vsb_psup)
    check_voltage('FPGA:BMC_VCC_3V3', lambda: read_pac_adc("pac_fpga", "VCCA"), 3.135, 3.465) #as (234), but from fpga perspective
    check_voltage('FPGA:BMC_VCC_5V', lambda: read_pac_adc("pac_fpga", "VCCINP"), 4.75, 5.25) #as (233), but from fpga perspective
    psup_on() #Initiate(b_psup_on)
    wait_for('PSUP_PGOOD', lambda: "IN1" in power.device_read("pac_cpu", "input_status"), True, 1) #None
    check_voltage('CPU:12V_CPU0_PSUP', lambda: read_pac_adc("pac_cpu", "VMON1"), 4.71, 5.19) #Complete(12v_cpu0_psup)
    check_voltage('CPU:5V_PSUP', lambda: read_pac_adc("pac_cpu", "VMON2"), 4.75, 5.25) #Complete(5v_psup)
    check_voltage('CPU:3V3_PSUP', lambda: read_pac_adc("pac_cpu", "VMON3"), 3.135, 3.465) #Complete(3v3_psup)
    check_voltage('FPGA:12V_CPU1_PSUP', lambda: read_pac_adc("pac_fpga", "VMON1"), 4.71, 5.19) #Complete(12v_cpu1_psup)
    check_voltage('FPGA:5V_PSUP', lambda: read_pac_adc("pac_fpga", "VMON2"), 4.75, 5.25) #same as (242) but from fpga perspective
    gpio.set_value('C_PLL_DCOK', False) #establish known state
    gpio.set_value('C_RESET_N', False) #establish known state
    gpio.set_value('B_OCI2_LNK1', False) #None
    gpio.set_value('B_OCI3_LNK1', False) #None
    program_clock_main() #Initiate(clk_main)
    program_clock_cpu() #Initiate(pll_ref_clk)
    program_clock_fpga() #Initiate(fpga_clk)
    program_ir3581() #Initiate(vdd_core) and Initiate(0v9_vdd_oct)
    wait_for('B_CLOCK_BLOL', lambda: gpio.get_value('B_CLOCK_BLOL'), True, 10) #None
    enable_pac_out('pac_cpu', 'OUT6') #Initiate(vdd_core_en)
    check_voltage('CPU:VDD_CORE', lambda: read_pac_adc("pac_cpu", "VMON4"), 0.94, 0.96) #Complete(vdd_core)
    enable_pac_out('pac_cpu', 'OUT7') #Initiate(vdd_oct_en_12)
    check_voltage('CPU:0V9_VDD_OCT', lambda: read_pac_adc("pac_cpu", "VMON5"), 0.87, 0.93) #Complete(0v9_vdd_oct)
    enable_pac_out('pac_cpu', 'OUT8') #Initiate(en_1v5_vdd_oct)
    check_voltage('CPU:1V5_VDD_OCT', lambda: read_pac_adc("pac_cpu", "VMON6"), 1.425, 1.575) #Complete(1v5_vdd_oct)
    enable_pac_out('pac_cpu', 'OUT9') #Initiate(en_2v5_cpu13)
    check_voltage('CPU:2V5_CPU13', lambda: read_pac_adc("pac_cpu", "VMON7"), 2.375, 2.625) #Complete(2v5_cpu13)
    enable_pac_out('pac_cpu', 'OUT10') #Initiate(en_2v5_cpu24)
    check_voltage('CPU:2V5_CPU24', lambda: read_pac_adc("pac_cpu", "VMON8"), 2.375, 2.625) #Complete(2v5_cpu24)
    enable_pac_out('pac_cpu', 'OUT11') #Initiate(en_vdd_ddrcpu13)
    #    check_voltage('CPU:VDD_DDRCPU13', lambda: read_pac_adc("pac_cpu", "VMON9"), 1, 1)
    #    check_voltage('CPU:VTT_DDRCPU13', lambda: read_pac_adc("pac_cpu", "VMON11"), 1, 1)
    enable_pac_out('pac_cpu', 'OUT12') #Initiate(en_vdd_ddrcpu24)
    #    check_voltage('CPU:VDD_DDRCPU24', lambda: read_pac_adc("pac_cpu", "VMON10"), 1, 1)
    #    check_voltage('CPU:VTT_DDRCPU24', lambda: read_pac_adc("pac_cpu", "VMON12"), 1, 1)
    enable_pac_out('pac_fpga', 'OUT6') #Initiate(en_util33)
    check_voltage('FPGA:UTIL_3V3', lambda: read_pac_adc("pac_fpga", "VMON3"), 3.135, 3.465) #Complete(util33)
    enable_pac_out('pac_fpga', 'OUT9') #Initiate(en_vccint_fpga)
    #    check_voltage('FPGA:VCCINT', lambda: read_pac_adc("pac_cpu", "VMON6"), 0.873, 0.923)
    enable_pac_out('pac_fpga', 'OUT13') #Initiate(en_vccintio_bram_fpga)
    check_voltage('FPGA:VCCINTIO_BRAM_FPGA', lambda: read_pac_adc("pac_fpga", "VMON10"), 0.873, 0.923, 1) #Complete(vccintio_bram_fpga)
    enable_pac_out('pac_fpga', 'OUT15') #Initiate(en_vcc1v8_fpga)
    check_voltage('FPGA:VCC1V8_FPGA', lambda: read_pac_adc("pac_fpga", "VMON11"), 1.71, 1.89) #Complete(vcc1v8_fpga)
    enable_pac_out('pac_fpga', 'OUT16') #Initiate(en_sys_1v8)
    check_voltage('FPGA:SYS_1V8', lambda: read_pac_adc("pac_fpga", "VMON12"), 1.71, 1.89) #Complete(sys_1v8)
    enable_pac_out('pac_fpga', 'OUT8') #Initiate(en_sys_2v5_24)
    check_voltage('FPGA:SYS_2V5_13', lambda: read_pac_adc("pac_fpga", "VMON5"), 2.375, 2.625) #Complete(sys_2v5_24)
    enable_pac_out('pac_fpga', 'OUT7') #Initiate(en_sys_2v5_13)
    check_voltage('FPGA:SYS_2V5_24', lambda: read_pac_adc("pac_fpga", "VMON4"), 2.375, 2.625) #Complete(sys_2v5_13)
    enable_pac_out('pac_fpga', 'OUT19') #Initiate(en_vdd_ddrfpga24)
    enable_pac_out('pac_fpga', 'OUT18') #Initiate(en_vdd_ddrfpga13)
    enable_pac_out('pac_fpga', 'OUT17') #Initiate(en_vadj_1v8_fpga)
    enable_pac_out('pac_fpga', 'OUT10') #Initiate(en_mgtavcc_fpga)
    check_voltage('FPGA:MGTAVCC_FPGA', lambda: read_pac_adc("pac_fpga", "VMON7"), 0.855, 0.945) #Complete(mgtavcc_fpga)
    enable_pac_out('pac_fpga', 'OUT14') #Initiate(en_mgtavtt_fpga)
    enable_pac_out('pac_fpga', 'OUT11') #Initiate(en_mgtvccaux_l)
    check_voltage('FPGA:MGTVCCAUX_L', lambda: read_pac_adc("pac_fpga", "VMON8"), 1.71, 1.89) #Complete(mgtvccaux_l)
    enable_pac_out('pac_fpga', 'OUT12') #Initiate(en_mgtvccaux_r)
    check_voltage('FPGA:MGTVCCAUX_R', lambda: read_pac_adc("pac_fpga", "VMON9"), 1.71, 1.89) #Complete(mgtvccaux_r)
    wait_for('B_CLOCK_CLOL', lambda: gpio.get_value('B_CLOCK_CLOL'), True, 10) #Initiate(pll_dc_ok)
    wait_for('B_CLOCK_FLOL', lambda: gpio.get_value('B_CLOCK_FLOL'), True, 10) #Initiate(clock_flol)
    gpio.set_value('C_PLL_DCOK', True) #tied to (292) in implementation
    gpio.set_value('C_RESET_N', True) #Initiate(c_reset_n)
    print('Power up complete')