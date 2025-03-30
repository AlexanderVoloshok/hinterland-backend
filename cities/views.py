import json
from flask import Blueprint, request
from cities.city import City, get_cities_list
from utils import valid_city


city_bp = Blueprint('cities', __name__)


@city_bp.route("/", methods=['GET'])
def get_available_cities():
    return get_cities_list()


@city_bp.route("/<city>/hinterland/<report_type>", methods=['GET'])
@valid_city
def dispatch_city_report_by_type(city: str, report_type: str):
    c = City(city)

    if report_type == 'numbers':
        return c.get_hinterland_numbers()
    elif report_type == 'dynamics': 
        arrg_type = request.args.get('groupBy')
        return c.get_hinterland_dynamics(arrg_type)
    elif report_type == 'map': 
        return c.hinterland_map()
    elif report_type == 'minmaxroutelength':
        return c.get_min_max_route_length_dynamics()
    elif report_type == 'centroids': 
        return c.centroid_migration()
    elif report_type == 'cities': 
        return c.destinations_list()
    
    return {"status": "bad", "error": "invalid city action"}, 403


@city_bp.route("/<city>/hinterland/change/<year_from>/<year_to>", methods=['GET'])
@valid_city
def get_hinterland_changes(city: str, year_from: int, year_to: int):
    c = City(city)
    return c.get_hinterland_changes(year_from, year_to)


@city_bp.route("/<city>/hinterland/<year>/distribution", methods=['GET'])
@valid_city
def get_route_length_distribution(city: str, year: str):
    try:
        year = int(year)
    except ValueError:
        return "invalid year", 403
    
    c = City(city)
    return c.get_route_length_distribution(year)


@city_bp.route("/<city>/routes/timeline", methods=['POST'])
@valid_city
def get_route_timeline(city: str):
    destinations = tuple(json.loads(request.data))
    c = City(city)
    return c.get_route_timeline(destinations)


@city_bp.route("/<city>/links", methods=['GET'])
@valid_city
def get_city_links(city: str):    
    c = City(city)
    return c.wiki_links


@city_bp.route("/<city>/airlines", methods=['GET'])
@valid_city
def get_airlines(city: str):    
    c = City(city)
    return c.airlines_list()