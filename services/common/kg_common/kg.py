from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF
from .sparql import run_update

SCHEMA = Namespace("http://kg.local/schema#")
DATA = Namespace("http://kg.local/data/")

def triples_to_turtle(triples, doc_id: str):
    g = Graph()
    g.bind("schema", SCHEMA)
    g.bind("data", DATA)

    for t in triples:
        s = URIRef(DATA + slugify(t["s"]))
        p = URIRef(SCHEMA + slugify(t["p"]))
        o_val = t["o"]
        if looks_entity(o_val):
            o = URIRef(DATA + slugify(o_val))
            g.add((s, p, o))
        else:
            g.add((s, p, Literal(o_val)))
    for t in triples:
        s = URIRef(DATA + slugify(t["s"]))
        g.add((s, RDF.type, SCHEMA.Entity))
    return g.serialize(format="turtle").decode("utf-8")

def looks_entity(x: str) -> bool:
    return any(c.isspace() for c in x) or (len(x)>0 and x[0].isupper())

def slugify(x: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in x).strip("_")

def upsert_triples(triples, doc_id: str):
    ttl = triples_to_turtle(triples, doc_id)
    update = f"""
    INSERT DATA {{
{ttl}
    }}
    """
    return run_update(update)
