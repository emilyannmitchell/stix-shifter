import importlib
from stix_shifter.stix_translation.src.patterns.parser import generate_query
from stix2patterns.validator import run_validator
from stix_shifter.stix_translation.src.stix_pattern_parser import parse_stix
import re
from ..utils.error_response import ErrorResponder
from .src.exceptions import DataMappingException, StixValidationException, UnsupportedDataSourceException, TranslationResultException
import sys


TRANSLATION_MODULES = ['qradar', 'dummy', 'car', 'cim', 'splunk', 'elastic', 'bigfix', 'csa', 'csa:at', 'csa:nf', 'aws_security_hub', 'carbonblack']
RESULTS = 'results'
QUERY = 'query'
DEFAULT_LIMIT = 10000
DEFAULT_TIMERANGE = 5


class StixTranslation:
    """
    StixShifter class - implements translations of stix data
    """

    def __init__(self):
        self.args = []

    def translate(self, module, translate_type, data_source, data, options={}, recursion_limit=1000):
        """
        Translated queries to a specified format
        :param module: What module to use
        :type module: one of TRANSLATION_MODULES 'qradar', 'dummy'
        :param translate_type: translation of a query or result set must be either 'results' or 'query'
        :type translate_type: str
        :param data: the data to translate
        :type data: str
        :param options: translation options { stix_validator: bool }
        :type options: dict
        :param recursion_limit: maximum depth of Python interpreter stack
        :type recursion_limit: int
        :return: translated results
        :rtype: str
        """
        dialect = None
        mod_dia = module.split(':', 1)
        module = mod_dia[0]
        if len(mod_dia) > 1:
            dialect = mod_dia[1]

        try:
            if module not in TRANSLATION_MODULES:
                raise UnsupportedDataSourceException("{} is an unsupported data source.".format(module))

            translator_module = importlib.import_module(
                "stix_shifter.stix_translation.src.modules." + module + "." + module + "_translator")

            if dialect is not None:
                interface = translator_module.Translator(dialect=dialect)
            else:
                interface = translator_module.Translator()

            if translate_type == QUERY:
                # Increase the python recursion limit to allow ANTLR to parse large patterns
                current_recursion_limit = sys.getrecursionlimit()
                if current_recursion_limit < recursion_limit:
                    print("Changing Python recursion limit from {} to {}".format(current_recursion_limit, recursion_limit))
                    sys.setrecursionlimit(recursion_limit)
                if 'result_limit' not in options:
                    options['result_limit'] = DEFAULT_LIMIT
                if 'timerange' not in options:
                    options['timerange'] = DEFAULT_TIMERANGE
                errors = []
                # Temporarily skip validation on patterns with START STOP qualifiers: validator doesn't yet support timestamp format
                start_stop_pattern = "START\s?t'\d{4}(-\d{2}){2}T\d{2}(:\d{2}){2}(\.\d+)?Z'\sSTOP"
                pattern_match = re.search(start_stop_pattern, data)
                if (not pattern_match):
                    errors = run_validator(data)
                if (errors != []):
                    raise StixValidationException(
                        "The STIX pattern has the following errors: {}".format(errors))
                else:
                    # Translating STIX pattern to antlr query object
                    query_object = generate_query(data)
                    # Converting query object to datasource query
                    parsed_stix_dictionary = parse_stix(query_object, options['timerange'])
                    parsed_stix = parsed_stix_dictionary['parsed_stix']
                    start_time = parsed_stix_dictionary['start_time']
                    end_time = parsed_stix_dictionary['end_time']
                    # Todo: pass in the query_object instead of the data so we can remove multiple generate_query calls.
                    # Converting STIX pattern to datasource query
                    queries = interface.transform_query(data, options)
                    return {'queries': queries, 'parsed_stix': parsed_stix, 'start_time': start_time, 'end_time': end_time}
            elif translate_type == RESULTS:
                # Converting data from the datasource to STIX objects
                try:
                    return interface.translate_results(data_source, data, options)
                except Exception:
                    raise TranslationResultException()
            else:
                raise NotImplementedError('wrong parameter: ' + translate_type)
        except Exception as ex:
            print('caught exception: ' + str(ex) + " " + str(type(ex)))
            response = dict()
            ErrorResponder.fill_error(response, message_struct={'exception': ex})
            return response
