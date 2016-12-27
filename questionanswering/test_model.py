import click
import yaml
import numpy as np
import logging
from models import char_based

from datasets import webquestions_io


@click.command()
@click.argument('path_to_model')
@click.argument('config_file_path', default="default_config.yaml")
def test_model(path_to_model, config_file_path):
    """

    :param path_to_model:
    :param config_file_path:
    :return:
    """
    with open(config_file_path, 'r') as config_file:
        config = yaml.load(config_file.read())
    print(config)
    config_global = config.get('global', {})
    np.random.seed(config_global.get('random_seed', 1))

    logger = logging.getLogger(__name__)
    logger.setLevel(config['logger']['level'])
    ch = logging.StreamHandler()
    ch.setLevel(config['logger']['level'])
    logger.addHandler(ch)

    if "webquestions" not in config:
        print("Dataset location not in the config file!")
        exit()

    webquestions = webquestions_io.WebQuestions(config['webquestions'])
    trainablemodel = char_based.CharCNNModel(parameters=config.get('model', {}), logger=logger)
    trainablemodel.load_from_file(path_to_model)

    print("Testing the model on silver data.")
    trainablemodel.test_on_silver(webquestions.get_validation_samples())

    if config.get("wikidata", False):
        print("Testing the model on gold answers.")
        validation_graph_lists, validation_gold_answers = webquestions.get_validation_with_gold()
        print("Evaluate on {} validation questions.".format(len(validation_gold_answers)))
        trainablemodel.test((validation_graph_lists, validation_gold_answers), verbose=True)


if __name__ == "__main__":
    test_model()