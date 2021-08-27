#! /usr/bin/env python3
import argparse

from sequence_generation import Topology, State_Search_Flags

def enzian_sequence_gen(outfile):
    from enzian_descriptions import enzian_nodes, enzian_wires
    enzian = Topology(enzian_nodes, enzian_wires)
    enzian.stateful_node_update({"cpu": "POWERED_ON", "fpga": "POWERED_ON"}, flags=State_Search_Flags(all_solutions=False))
    enzian.done(outfile)

platforms = {
    "enzian": enzian_sequence_gen
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generates power up sequences from declarative platform descriptions")
    parser.add_argument("platform", choices=["enzian"],
        help="Platform for which to generate the sequence. Currently only Enzian is supported."
    )
    parser.add_argument("--out", "-o", type=str, required=True, metavar="FILE",
        help="File to which the sequence is saved"
    )
    args = parser.parse_args()

    platforms[args.platform](args.out)
