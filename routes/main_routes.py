# -*- coding: utf-8 -*-

import os
from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    return render_template("index.html")


@main_bp.get("/voltage/results")
def voltage_results():
    result_dir = os.path.join(os.getcwd(), "test_results")
    files = []
    if os.path.isdir(result_dir):
        for f in os.listdir(result_dir):
            if f.endswith(".csv"):
                fpath = os.path.join(result_dir, f)
                size_kb = os.path.getsize(fpath) // 1024
                files.append({"name": f, "size": size_kb})
    files.sort(key=lambda x: x["name"], reverse=True)
    return render_template("voltage_results.html", files=files)


@main_bp.get("/voltage/set")
def voltage_set_page():
    return render_template("voltage_set.html")


@main_bp.get("/power/cycle")
def power_cycle_page():
    return render_template("power_cycle.html")


@main_bp.get("/temp/scan")
def temp_scan_page():
    return render_template("temp_scan.html")

