#! /usr/bin/env python3

import argparse
import sys
import pandas
import matplotlib.pyplot as plt
import numpy as np

M1 = [
    ("eval1_m1_p1.csv", "p1", "blue", "o"),
    ("eval1_m1_p2.csv", "p2", "orange", "^"),
    ("eval1_m1_p3.csv", "p3", "black", "+"),
]

M2 = [
    ("eval1_m2_p1.csv", "p1", 0),
    ("eval1_m2_p2.csv", "p2", 1),
    ("eval1_m2_p3.csv", "p3", 2),
]

M3 = [
    ("eval1_m3_p1.csv", "p1"),
    ("eval1_m3_p2.csv", "p2"),
    ("eval1_m3_p3.csv", "p3"),
]


M4 = [
    ("eval1_m4_p1.csv", "p1", "blue", "o"),
    ("eval1_m4_p2.csv", "p2", "orange", "^"),
    ("eval1_m4_p3.csv", "p3", "black", "+"),
]


def plot_m1():
    plt.figure(figsize= (6, 2.5))
    for (path, problem, colour, symbol) in M1:
        data = pandas.read_csv("results/" + path, header = None)
        x = data[0].values
        y = data[1].values
        plt.plot(x, y, symbol, color = colour, markersize=3.5, label=problem)
    plt.title("Comparison of Advanced and Naive Backtracking (M1)")
    plt.ylabel("advanced backtracking [s]")
    plt.yscale("linear")
    plt.xscale("log")
    begin, end = plt.ylim()
    t = np.arange(begin, end, 0.01)
    plt.plot(t, t, color = "red", label = "f(x) = x")

    plt.xlabel("naive backtracking [s]")
    plt.legend()
    plt.tight_layout()
    plt.savefig("plots/eval1_m1.png", dpi = 800)
    plt.show()

    plt.figure(figsize = (4, 3))
    data_vector = None
    colours = []
    labels = []
    for (path, problem, colour, symbol) in M1:
        data = pandas.read_csv("results/" + path, header = None)
        x = data[2].values[:100]
        x = np.reshape(x, (-1, 1))
        if data_vector is None:
            data_vector = x
        else:
            data_vector = np.hstack((data_vector, x))
        colours.append(colour)
        labels.append(problem)
    plt.hist(data_vector, color = colours, label=labels)
    plt.title("Histogram of Z3 Runtime Measurements (M1)")
    plt.xlabel("z3 solver [s]")
    plt.ylabel("number of measurements")
    plt.legend()
    plt.tight_layout()
    plt.savefig("plots/eval_m1_Z3.png", dpi = 800)
    plt.show()


def plot_m2():
    for (path, problem, _) in M2:
        plt.figure(figsize= (5.5, 2.5))
        plt.subplot(1, 1, 1)
        hist_data = pandas.read_csv("results/" + path, header=None)[0].values
        threshold = 2
        outliers = np.extract(np.greater(hist_data, threshold), hist_data)
        normal_values = np.extract(np.less_equal(hist_data, threshold), hist_data)
        minimum = np.min(hist_data)
        maximum = np.max(hist_data)
        print(maximum)
        data = np.minimum(hist_data, threshold)
        bins = np.linspace(minimum, threshold, 30)
        plt.subplot(1, 2, 1)
        plt.hist(normal_values, bins = bins)
        plt.ylabel("number of measurements")
        plt.xlabel("runtime advanced backtracking [s]")
        ax = plt.subplot(1, 2, 2)
        if maximum > threshold:
            x, y, _ = plt.hist(outliers, bins= np.linspace(threshold, maximum, 30), color = "red")
            largest_num = int(x.max()) + 2
            yint = range(largest_num)
            plt.yticks(yint)
            plt.ylabel("number of measurements")
            plt.xlabel("runtime advanced backtracking [s]")
        else:
            plt.text(0.5, 0.5, "None", horizontalalignment='center', verticalalignment='center', transform = ax.transAxes)
            plt.ylabel("number of measurements")
            plt.xlabel("runtime advanced backtracking [s]")
            plt.yticks(range(0, 2))
            plt.xlim((2, 10))
        plt.title("outliers")
        plt.tight_layout()
        plt.savefig("plots/eval1_m2_%s.png"%problem, dpi=800)
        plt.show()

def plot_m3():
    for (path, problem) in M3:
        plt.figure(figsize= (4, 2.5))
        hist_data = pandas.read_csv("results/" + path, header=None)[0].values
        maximum = np.max(hist_data)
        print(maximum)
        bins = np.linspace(0, maximum, 50)
        plt.hist(hist_data, bins = bins)
        plt.ylabel("number of measurements")
        plt.xlabel("runtime advanced backtracking [s]")
        plt.tight_layout()
        plt.savefig("plots/eval1_m3_%s.png"%problem, dpi = 800)
        plt.show()    


def plot_m4():
    plt.figure(figsize = (6, 3))
    for (path, problem, colour, symbol) in M4:
        data = pandas.read_csv("results/" + path, header = None)
        x = data[0].values
        y = data[1].values
        plt.plot(x, y, symbol, color = colour, markersize=3.5, label=problem)
    begin, end = plt.ylim()
    t = np.arange(begin, end, 0.01)
    plt.plot(t, t, color = "red", label = "f(x) = x")
    plt.title("Effect of State Restriction (M4)")
    plt.ylabel("restricted states [s]")
    plt.xlabel("unrestricted states [s]")
    plt.legend()
    plt.tight_layout()
    plt.savefig("plots/eval1_m4.png", dpi = 800)
    plt.show()

plots = {
    "m1": plot_m1,
    "m2": plot_m2,
    "m3": plot_m3,
    "m4": plot_m4
}
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot evaluation 1 results, by default all plots are generated.")
    parser.add_argument("--m1", dest="plots", const="m1", action="append_const",
        help="Plot results for measurement 1"
    )
    parser.add_argument("--m2", dest="plots", const="m2", action="append_const",
        help="Plot results for measurement 2"
    )
    parser.add_argument("--m3", dest="plots", const="m3", action="append_const",
        help="Plot results for measurement 3"
    )
    parser.add_argument("--m4", dest="plots", const="m4", action="append_const",
        help="Plot results for measurement 4"
    )
    args = parser.parse_args()

    if args.plots is None:
        ps = plots.keys()
    else:
        ps = args.plots

    for p in ps:
        try:
            plots[p]()
        except FileNotFoundError as e:
            print(f"Plot '{p}' failed: '{e.filename}' doesn't exist.", file=sys.stderr)
