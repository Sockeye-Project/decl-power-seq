# Declarative Power Sequencing

This is the artifact for the ACM TECS article presented at EMSOFT 2021.

## TL;DR
To reproduce the results from the article run `make paper-results`.
This has been tested on Ubuntu 18.04 and 20.04, you might need to install `python3-venv` for it to work.

## Repository Structure
 - `sequence_generation.py`: Contains the code for the declarative power sequencing framework (classes for the model  and algorithms).
 - `enzian_descriptions.py`: Model instance for the [Enzian Research Computer](http://www.enzian.systems).
 - `main.py`: Main entry point to generate power up sequences
 - `evaluation.py`: Runs the evaluation for the model
 - `manual_sequence.py`, `manual_sequence_event_graph.txt`: Manually developed sequence for Enzian, baseline to compare generated sequences against.
 - `visualize.py`: Experimental framework to visualize sequences.
 - `tests.py`: Unit tests for the framework.

 ## Dependencies
The code has been tested to work on Ubuntu 18.04 and 20.04.
The code needs Python 3 (tested with  3.6.9 and 3.8.10).
It also needs `matplotlib`, `numpy`, `pandas` and for some functionality `z3-solver`.
Those can be installed using `pip`.
We also provide a requirements file.
We recommend using a virtual environment, the venv module can be installed with `apt-get install python3-venv` on Ubuntu.
The make target `venv` automates the creation of the virtual environment.

## Generating sequences
To generate a full power sequence for Enzian run `./main.py -o OUT_FILE enzian`.
This will store the sequence to the given OUT_FILE.
This is how we generate the sequence for Section 6.1 in the article.

## Evaluation Results
The results in Section 6.2 in the article can be reproduced running `./evaluation.py --e1m2` to run the experiment followed by `./plots --m2` to generate the plots.
The raw data is saved to `results/eval1_m2_p{1,2,3}.csv`, the plots are saved to `plots/eval1_m2_p{1,2,3}.png`.

The experiment in Section 6.3 can be run with `./evaluation.py --e2`.
The data will be saved to `results/eval2.csv`.

There are a few more experiments that aren't in the article.
See [Jasmin Schult's Bachelor's thesis](https://doi.org/10.3929/ethz-b-000490632) for detailed descriptions of these.
