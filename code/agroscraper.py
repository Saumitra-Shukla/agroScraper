#!/bin/env python3
# -*- coding: utf-8 -*-

"""
Extracting information from transparenzdatenbank.at

Output from the #gutedaten Hackathon in Graz, Sat. 28. Nov. 2015

"""


__author__ = "Christopher Kittel"
__copyright__ = "Copyright 2015"
__license__ = "MIT"
__version__ = "0.0.3"
__maintainer__ = "Christopher Kittel"
__email__ = "web@christopherkittel.eu"
__status__ = "Prototype" # 'Development', 'Production' or 'Prototype'


import requests

import os
import sys
import argparse

import json
import csv


parser = argparse.ArgumentParser(description='Extracts structured data from transparenzdatenbank.at and exports it to JSON and CSV.')
parser.add_argument('--output', dest='outputfolder', help='relative or absolute path of the output folder')
parser.add_argument('--year', dest='year', help='year of funding data to request')
args = parser.parse_args()

overall_outfile = "_".join(["agrofunding", args.year]) + ".json"
details_outfile = "_".join(["agrofunding", "details", args.year]) + ".json"
csv_outfile = "_".join(["agrofunding", args.year]) + ".csv"

def drawProgressBar(percent, barLen = 20):
    """
    Draw a progress bar to the command line.
    """
    sys.stdout.write("\r")
    progress = ""
    for i in range(barLen):
        if i < int(barLen * percent):
            progress += "="
        else:
            progress += " "
    sys.stdout.write("[ %s ] %.2f%%" % (progress, percent * 100))
    sys.stdout.flush()


def get_cache():
    """
    If nothing cached, get the raw data.
    Returns a tuple of dicts.
    """
    try: # load cached search
        with open(overall_outfile, "r") as infile:
            raw = json.load(infile)
    except: # if nothing cached
        raw = get_raw()
        # make a quick save
        with open(overall_outfile, "w") as outfile:
            json.dump(raw, outfile)

    try: # load cached details
        with open(details_outfile, "r") as infile:
            results = json.load(infile)
    except: # if nothing cached
        results = {}

    return raw, results

def get_missing_ids(raw, results):
    """
    Compare cached results with overall expected IDs, return missing ones.
    Returns a set.
    """
    all_ids = set(raw.keys())
    cached_ids = set(results.keys())
    print("There are {0} IDs in the dataset, we already have {1}. {2} are missing.".format(len(all_ids), len(cached_ids), len(all_ids) - len(cached_ids)))
    return all_ids - cached_ids

def get_raw():
    """
    Perform a POST to transparenzdatenbank asking for the overall raw data.
    Returns a dict.
    """
    url = 'http://transparenzdatenbank.at/suche'
    rawheader = {"Accept": "application/json, text/plain, */*",
               "Accept-Encoding": "gzip, deflate",
               "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
               "Content-Length": "100",
               "Content-Type": "application/json;charset=utf-8",
               "DNT": "1",
               "Host": "transparenzdatenbank.at",
               "PAGINATION_CURRENT": "1",
               "PAGINATION_PER_PAGE": "140000",
               "Referer": "http://transparenzdatenbank.at/",
               "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:42.0) Gecko/20100101 Firefox/42.0"
               }
    # json string
    payload = "{\"name\":\"\", \"betrag_von\":\"\", \"betrag_bis\":\"\", \
                \"gemeinde\":\"\", \"massnahme\":null, \
                \"jahr\":%s, \"sort\":\"name\"}" %args.year

    response = requests.request("POST", url, data=payload, headers = rawheader)
    raw = response.json()
    return {r.get("id"):r for r in raw}

def crawl(raw, results, missing_ids):
    """
    Add missing results by iterating over missing IDs.
    Returns a dict.
    """
    # for progress bar
    progress = 0.0
    maxi = len(missing_ids)

    i = 0
    for id_ in missing_ids:

        try:
            r = raw.get(id_)
            results[id_] = enhance_raw(r)

            # more progress
            progress += 1
            percent = progress/maxi
            drawProgressBar(percent)
        except: # some server/network error
            # store cache
            with open(details_outfile, "w") as outfile:
                json.dump(results, outfile)

        # dumps every 1000 entries to avoid losing progress to network errors
        i += 1
        if i > 1000:
            with open(details_outfile, "w") as outfile:
                json.dump(results, outfile)
            i = 0

    return results

def enhance_raw(r):
    """
    Reformat the raw data. Add the detailed information to a raw search result.
    Returns a dict.
    """
    result = {}
    result["id"] = int(r.get("id"))
    result["recipient"] = r.get("name")

    # missing values for plz
    if r.get("plz") is None:
        result["postcode"] = "NA"
    else:
        result["postcode"] = int(r.get("plz"))

    result["municipality"] = r.get("gemeinde")
    result["year"] = int(r.get("jahr"))
    result["total_amount"] = float(r.get("betrag"))
    result["details"] = get_details(r.get("id"))

    return result

def get_details(id_):
    """
    Perform GET requests for the transparenzdatenbank-search and returns
    detailed information for a funding ID.
    Returns a list.
    """
    # create new header for detailed search
    detailsheader = {'Host': 'transparenzdatenbank.at',
                     'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:42.0) Gecko/20100101 Firefox/42.0',
                     'Accept': 'application/json, text/plain, */*',
                     'Accept-Language': 'de,en-US;q=0.7,en;q=0.3',
                     'Accept-Encoding': 'gzip, deflate',
                     'DNT': '1',
                     'Referer': 'http://transparenzdatenbank.at/'
                     }
    searchurl = 'http://transparenzdatenbank.at/suche/details/%s/%s' %(id_, args.year)

    details = []
    rawdetails = requests.request("GET", searchurl, headers = detailsheader).json()
    for rd in rawdetails:
        detail = {}
        detail["id"] = int(rd.get("id"))
        detail["type"] = rd.get("bezeichnung")
        detail["description"] = rd.get("beschreibung")
        detail["partial_amount"] = float(rd.get("betrag"))
        details.append(detail)
    return details

def save2csv(results, filename):
    """
    Export the extracted data to agrofunding.csv with the following columns:
    "unique_id", "funding_id", "recipient", "year",
    "postcode", "municipality", "total_amount",
    "detail_id", "type", "partial_amount"
    """
    i = 0
    with open(filename, "w") as csvfile:
        agrowriter = csv.writer(csvfile, delimiter = ",", quotechar='"')
        agrowriter.writerow(["unique_id", "funding_id", "recipient", "year",
                            "postcode", "municipality", "total_amount",
                            "detail_id", "type", "partial_amount"])
        for result in results.values():
            metadata = [result.get("id"), result.get("recipient"),
                        result.get("year"), result.get("postcode"),
                        result.get("municipality"), result.get("total_amount")]
            for detail in result.get("details"):
                data = [detail.get("id"), detail.get("type"),
                                    detail.get("partial_amount")]
                agrowriter.writerow([i]+metadata+data)
                i += 1

def setup_folders(foldername):
    """
    Check whether outfolder folder and path exist, create them if necessary.
    """
    if not os.path.exists(foldername):
        os.makedirs(foldername)

def main(args):
    setup_folders(args.outputfolder)
    os.chdir(args.outputfolder)
    raw, old_results = get_cache()
    missing_ids = get_missing_ids(raw, old_results)
    new_results = crawl(raw, old_results, missing_ids)

    # store final
    with open(details_outfile, "w") as outfile:
        json.dump(new_results, outfile)

    save2csv(new_results, csv_outfile)


if __name__ == '__main__':
    main(args)
