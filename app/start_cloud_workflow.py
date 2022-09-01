import string
import json
import random
from datetime import datetime
from download_imerg import lambda_handler
from download_aggregate_modis import modis_handler

def find_maxmin_latlon(lat, lon, minlat, minlon, maxlat, maxlon):
    if lat > maxlat:
        maxlat = lat
    if lat < minlat:
        minlat = lat
    if lon > maxlon:
        maxlon = lon
    if lon < minlon:
        minlon = lon
    return minlat, minlon, maxlat, maxlon


def start_process(event):
    # print("Event: ", event)
    dataset = event["dataset"]
    org_unit = event['org_unit']
    period = event['agg_period']
    start_date = event['start_date']
    end_date = event['end_date']
    data_element_id = event['data_element_id']
    boundaries = event['boundaries']
    request_id = ''.join(
        random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(10))
    # set some defaults
    # statType='median'
    statType = 'none'
    product = 'none'
    var_name = 'none'
    # "stat_type":"mean", "product": "GPM_3IMERGDL_06", "var_name": "HQprecipitation"
    if "stat_type" in event:
        statType = event['stat_type']
    if "product" in event:
        product = event['product']
    if "var_name" in event:
        var_name = event['var_name']

    # added for new json format
    districts = boundaries

    # find the max/min lat, lons for the coordinates
    minlat = 90.0
    maxlat = -90.0
    minlon = 180.0
    maxlon = -180.0
    for district in districts:
        shape = district['geometry']
        coords = district['geometry']['coordinates']
        #       name = district['properties']['name']
        dist_name = district['name']
        dist_id = district['id']

        if shape["type"] == "Polygon":
            for subregion in coords:
                for coord in subregion:
                    minlat, minlon, maxlat, maxlon = find_maxmin_latlon(coord[1], coord[0], minlat, minlon, maxlat,
                                                                        maxlon)
        elif shape["type"] == "MultiPolygon":
            for subregion in coords:
                #            print("subregion")
                for sub1 in subregion:
                    #                print("sub-subregion")
                    for coord in sub1:
                        minlat, minlon, maxlat, maxlon = find_maxmin_latlon(coord[1], coord[0], minlat, minlon,
                                                                            maxlat, maxlon)
        else:
            print
            "Skipping", dist_name, \
            "because of unknown type", shape["type"]

    # datetime object containing current date and time
    now = datetime.now()
    date_st = now.strftime("%m-%d-%YT%H:%M:%SZ")
    print("process started: " + date_st)

    # format new json structure
    downloadJson = {"dataset": dataset, "org_unit": org_unit, "agg_period": period, "start_date": start_date,
                    "end_date": end_date, "data_element_id": data_element_id, "request_id": request_id,
                    "min_lat": minlat, "max_lat": maxlat, "min_lon": minlon, "max_lon": maxlon,
                    "creation_time": date_st}
    if statType != 'none':
        downloadJson["stat_type"] = statType
    if product != 'none':
        downloadJson["product"] = product
    if var_name != 'none':
        downloadJson["var_name"] = var_name
    if 'x_start_stride_stop' in event:
        downloadJson["x_start_stride_stop"] = event["x_start_stride_stop"]
    if 'y_start_stride_stop' in event:
        downloadJson["y_start_stride_stop"] = event["y_start_stride_stop"]
    if 'dhis_dist_version' in event:
        downloadJson["dhis_dist_version"] = event["dhis_dist_version"]
    if 'auth_name' in event:
        downloadJson["auth_name"] = event["auth_name"]
    if 'auth_pw' in event:
        downloadJson["auth_pw"] = event["auth_pw"]
    if 'hv_tilelist' in event:
        downloadJson["hv_tilelist"] = event["hv_tilelist"]  # i.e. [[20,11],[20,10]]  modis h,v sinusoidal tile indices
    if 'modis_version' in event:
        downloadJson["modis_version"] = event[
            "modis_version"]  # version of MODIS file used in OpenDap links (i.e. "61" for 6.1)

    download_param_pathname = ""
    if dataset.lower() == 'precipitation' or dataset.lower() == 'temperature' \
            or dataset.lower() == 'vegetation':
        download_param_pathname = "requests/download/" + dataset + "/"
        # set up download_imerg data
    else:
        return dict(statusCode='200', headers={'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*',
                                               'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                                               'Access-Control-Allow-Methods': 'DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT'},
                    body=json.dumps({'message': "illegal dataset: " + dataset}), isBase64Encoded='false')

    # write out boundaries json file
    # format new json structure
    geometryJson = {"request_id": request_id, "boundaries": districts}
    geometry_pathname = "requests/geometry/"

    with open("/tmp/" + request_id + "_geometry.json", 'w') as geometry_file:
        json.dump(geometryJson, geometry_file)

    geometry_file.close()


    # write out download parameter file to S3 bucket to trigger download/aggregation

    with open("/tmp/" + request_id + ".json", 'w') as json_file:
        json.dump(downloadJson, json_file)
    #        json.dump(districtPrecipStats, json_file)
    json_file.close()

    # print(dataset)
    if dataset.lower() == 'precipitation':
        print("Calling the handler for: "+dataset)
        lambda_handler(downloadJson)

    elif dataset.lower() == 'temperature' or 'vegetation':
        print("Calling the handler for: " + dataset)
        modis_handler(downloadJson)

    return ({'request_id': request_id, "json": downloadJson, })