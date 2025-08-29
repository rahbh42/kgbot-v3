import requests
from .config import SPARQL_QUERY_URL, SPARQL_UPDATE_URL

def run_select(query: str):
    r = requests.post(SPARQL_QUERY_URL, data={"query": query}, headers={"Accept":"application/sparql-results+json"})
    r.raise_for_status()
    return r.json()

def run_update(update: str):
    r = requests.post(SPARQL_UPDATE_URL, data={"update": update})
    r.raise_for_status()
    return True
