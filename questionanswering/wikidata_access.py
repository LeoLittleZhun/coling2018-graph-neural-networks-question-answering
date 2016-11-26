import nltk
from SPARQLWrapper import SPARQLWrapper, JSON
import logging
import re


logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

sparql = SPARQLWrapper("http://knowledgebase:8890/sparql")
sparql.setReturnFormat(JSON)
sparql.setMethod("GET")
sparql.setTimeout(40)

sparql_prefix = """
        PREFIX e:<http://www.wikidata.org/entity/>
        PREFIX rdfs:<http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos:<http://www.w3.org/2004/02/skos/core#>
        PREFIX base:<http://www.wikidata.org/ontology#>
        """
sparql_select = """
        SELECT DISTINCT %queryvariables% WHERE
        """
sparql_relation = {
    "direct": "{GRAPH <http://wikidata.org/statements> { ?e1 ?p ?m . ?m ?rd ?e2 . %restriction% }}",

    "reverse": "{GRAPH <http://wikidata.org/statements> { ?e2 ?p ?m . ?m ?rr ?e1 . %restriction% }}",

    "v-structure": "{GRAPH <http://wikidata.org/statements> { ?m ?p ?e2 . ?m ?rv ?e1 . %restriction% }}",
}
sparql_relation_complex = """
        {
        {GRAPH <http://wikidata.org/statements> { ?e1 ?p ?m . ?m ?rd ?e2 . }}
        UNION
        {GRAPH <http://wikidata.org/statements> { ?e2 ?p ?m . ?m ?rr ?e1 . }}
        UNION
        {GRAPH <http://wikidata.org/statements> { ?m ?p ?e2. ?m ?rv ?e1. }}}
        """

sparql_entity_label = """
        {{GRAPH <http://wikidata.org/terms> { ?e2 rdfs:label "%labelright%"@en  }}
        UNION
        {GRAPH <http://wikidata.org/terms> { ?e2 skos:altLabel "%labelright%"@en  }}
        }
        """

sparql_relation_time_argmax = "?m ?a [base:time ?n]."

sparql_close_order = " ORDER BY {} LIMIT 1"

HOP_UP_RELATIONS = ["P131", "P31", "P279", "P17", "P361"]

sparql_entity_abstract = "[ _:s [ {} ?e2]]".format("|".join(["e:{}v".format(r) for r in HOP_UP_RELATIONS]))


def graph_to_query(g, return_var_values = False):
    """
    Convert graph to a sparql query.
    :param g: a graph as a dictionary with non-empty edgeSet
    :param return_var_values: if True the denotations for free variables will be returned
    :return: a sparql query
    >>> g = {'edgeSet': [{'left': [0], 'kbID': 'P35v', 'type': 'reverse', 'rightkbID': 'Q155', 'right': [5], 'argmax':'time'}], 'entities': []}
    >>> len(query_wikidata(graph_to_query(g, return_var_values = True)))
    1
    >>> g = {'edgeSet': [{'left': [0], 'kbID': 'P35v', 'type': 'reverse', 'rightkbID': 'Q155', 'right': [5]}], 'entities': []}
    >>> len(query_wikidata(graph_to_query(g, return_var_values = True)))
    5
    >>> g = {'edgeSet': [{'left': [0], 'right': [6]}], 'entities': [[4]], 'tokens': ['who', 'are', 'the', 'current', 'senator', 'from', 'missouri', '?']}
    >>> len(query_wikidata(graph_to_query(g, return_var_values = False)))
    160
    """
    query = sparql_prefix
    variables = []
    order_by = []
    query += sparql_select
    query += "{"
    for i, edge in enumerate(g.get('edgeSet', [])):
        if 'type' in edge:
            sparql_relation_inst = sparql_relation[edge['type']]
        else:
            sparql_relation_inst = sparql_relation_complex

        if 'kbID' in edge:
            sparql_relation_inst = re.sub(r"\?r[drv]", "e:" + edge['kbID'], sparql_relation_inst)
        else:
            sparql_relation_inst = sparql_relation_inst.replace("?r", "?r" + str(i))
            #             variables.extend(["?r{}".format(i), "?r{}r".format(i), "?r{}v".format(i) ])
            variables.extend(["?r{}{}".format(i, t[0]) for t in sparql_relation] if 'type' not in edge else ["?r{}{}".format(i, edge['type'][0])])

        if 'hopUp' in edge:
            sparql_relation_inst = sparql_relation_inst.replace("?e2", sparql_entity_abstract)

        if 'argmax' in edge:
            sparql_relation_inst = sparql_relation_inst.replace("%restriction%", sparql_relation_time_argmax)
            sparql_relation_inst = sparql_relation_inst.replace("?n", "?n" + str(i))
            sparql_relation_inst = sparql_relation_inst.replace("?a", "?a" + str(i))
            order_by.append("?n" + str(i))
        else:
            sparql_relation_inst = sparql_relation_inst.replace("%restriction%", "")


        sparql_relation_inst = sparql_relation_inst.replace("?p", "?p" + str(i))
        sparql_relation_inst = sparql_relation_inst.replace("?m", "?m" + str(i))

        if 'rightkbID' in edge:
            sparql_relation_inst = sparql_relation_inst.replace("?e2", "e:" + edge['rightkbID'])
        else:
            sparql_relation_inst = sparql_relation_inst.replace("?e2", "?e2" + str(i))
            right_label = " ".join([g['tokens'][i] for i in edge['right']]).title()
            sparql_entity_label_inst = sparql_entity_label.replace("?e2", "?e2" + str(i))
            sparql_entity_label_inst = sparql_entity_label_inst.replace("%labelright%", right_label)
            variables.append("?e2" + str(i))
            query += sparql_entity_label_inst
        sparql_relation_inst = sparql_relation_inst.replace("_:m", "_:m" + str(i))
        sparql_relation_inst = sparql_relation_inst.replace("_:s", "_:s" + str(i))

        query += sparql_relation_inst

    if return_var_values:
        variables.append("?e1")
    query += "}"
    query = query.replace("%queryvariables%", " ".join(variables))
    if order_by:
        order_by_pattern = sparql_close_order.format(" ".join(["DESC({})".format(v) for v in order_by]))
        query += order_by_pattern

    logger.debug("Querying with variables: {}".format(variables))
    return query


def get_free_variables(g, include_question_variable=False):
    free_variables = []
    for i, edge in enumerate(g.get('edgeSet', [])):
        if 'kbID' not in edge:
            free_variables.extend(["?r{}{}".format(i, t[0]) for t in sparql_relation] if 'type' not in edge else ["?r{}{}".format(i, edge['type'][0])])
        if 'rightkbID' not in edge:
            free_variables.append("?e2" + str(i))
    if include_question_variable:
        free_variables.append("?e1")
    return free_variables


def link_entity():
    pass


def query_wikidata(query):
    sparql.setQuery(query)
    try:
        results = sparql.query().convert()
    except Exception as inst:
        logger.debug(inst)
        return []
    if len(results["results"]["bindings"]) > 0:
        results = results["results"]["bindings"]
        logger.debug("Results bindings: {}".format(results[0].keys()))
        results = [r for r in results if all(r[b]['value'].startswith("http://www.wikidata.org/entity/") for b in r)]
        results = [{b: r[b]['value'].replace("http://www.wikidata.org/entity/", "") for b in r} for r in results]
        return results
    else:
        logger.debug(results)
        return []


def load_entity_map(path_to_map):
    try:
        with open(path_to_map) as f:
            return_map = [l.strip().split("\t") for l in f.readlines()]
        return nltk.Index({(t[1], t[0]) for t in return_map})
    except Exception as ex:
        logger.error("No entity map found. {}".format(ex))
        return {}

entity_map = load_entity_map("../data/" + "entity_map.tsv")


def map_query_results(query_results, question_variable='e1'):
    """
    Extract the variable values from the query results and map them to canonical WebQuestions strings.

    :param query_results: list of dictionaries returned by the sparql endpoint
    :param question_variable: the variable to extract
    :return: list of answers as entity labels or an original id if no canonical label was found.
    >>> map_query_results([{'e1':'Q76'}, {'e1':'Q235234'}])
    ['barack obama', 'q235234']
    """
    answers = [r[question_variable] for r in query_results]
    answers = [e.lower() for a in answers for e in entity_map.get(a, [a])]
    return answers


if __name__ == "__main__":
    import doctest
    print(doctest.testmod())
