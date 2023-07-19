"""Welcome to PyTabular.

__init__.py will start to setup the basics.
It will setup logging and make sure Pythonnet is good to go.
Then it will begin to import specifics of the module.
"""
# flake8: noqa
import logging
import os
import platform
import sys

# from rich import pretty
# from rich.console import Console
# from rich.logging import RichHandler
# from rich.theme import Theme

pretty.install()
# console = Console(theme=Theme({"logging.level.warning": "bold reverse red"}))
# logging.basicConfig(
#     level=logging.DEBUG,
#     format="%(message)s",
#     datefmt="[%H:%M:%S]",
#     # handlers=[RichHandler(console=console)],
# )
logger = logging.getLogger("PyTabular")
# logger.setLevel(logging.INFO)
# logger.info("Logging configured...")
# logger.info("To update logging:")
# logger.info(">>> import logging")
# logger.info(">>> pytabular.logger.setLevel(level=logging.INFO)")
# logger.info("See https://docs.python.org/3/library/logging.html#logging-levels")


# logger.info(f"Python Version::{sys.version}")
# logger.info(f"Python Location::{sys.exec_prefix}")
# logger.info(f"Package Location:: {__file__}")
# logger.info(f"Working Directory:: {os.getcwd()}")
# logger.info(f"Platform:: {sys.platform}-{platform.release()}")

dll = os.path.join(os.path.dirname(__file__), "dll")
sys.path.append(dll)
sys.path.append(os.path.dirname(__file__))

logger.info("Beginning CLR references...")
import clr

logger.info("Adding Reference Microsoft.AnalysisServices.AdomdClient")
clr.AddReference("Microsoft.AnalysisServices.AdomdClient")
logger.info("Adding Reference Microsoft.AnalysisServices.Tabular")
clr.AddReference("Microsoft.AnalysisServices.Tabular")
logger.info("Adding Reference Microsoft.AnalysisServices")
clr.AddReference("Microsoft.AnalysisServices")

logger.info("Importing specifics in module...")
from .best_practice_analyzer import BPA
from .document import ModelDocumenter
from .logic_utils import (pandas_datatype_to_tabular_datatype,
                          pd_dataframe_to_m_expression)
from .pbi_helper import find_local_pbi_instances
from .pytabular import Tabular
from .query import Connection
from .tabular_editor import TabularEditor
from .tabular_tracing import BaseTrace, QueryMonitor, RefreshTrace

logger.info("Import successful...")
