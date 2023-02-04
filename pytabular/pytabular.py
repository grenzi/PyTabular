"""
`pytabular.py` is where it all started. So there is a lot of old methods that will eventually be deprecated.
Main class is `Tabular()`. Use that for connecting with your models.
"""
import logging

from Microsoft.AnalysisServices.Tabular import (
    Server,
    ColumnType,
    Table,
    DataColumn,
    Partition,
    MPartitionSource,
)

from typing import List, Union
from collections import namedtuple
import pandas as pd
import os
import subprocess
import atexit
from logic_utils import (
    pd_dataframe_to_m_expression,
    pandas_datatype_to_tabular_datatype,
    remove_suffix,
    remove_file,
)

from table import PyTable, PyTables
from partition import PyPartitions
from column import PyColumns
from measure import PyMeasures
from culture import PyCultures, PyCulture
from relationship import PyRelationship, PyRelationships
from object import PyObject
from refresh import PyRefresh
from query import Connection

logger = logging.getLogger("PyTabular")


class Tabular(PyObject):
    """Tabular Class to perform operations: [Microsoft.AnalysisServices.Tabular](https://docs.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.tabular?view=analysisservices-dotnet). You can use this class as your main way to interact with your model.

    Args:
            connection_str (str): Valid [Connection String](https://docs.microsoft.com/en-us/analysis-services/instances/connection-string-properties-analysis-services?view=asallproducts-allversions) for connecting to a Tabular Model.
    Attributes:
            Server (Server): See [Server MS Docs](https://docs.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.server?view=analysisservices-dotnet).
            Catalog (str): Name of Database. See [Catalog MS Docs](https://learn.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.connectioninfo.catalog?view=analysisservices-dotnet#microsoft-analysisservices-connectioninfo-catalog).
            Model (Model): See [Model MS Docs](https://learn.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.tabular.model?view=analysisservices-dotnet).
            AdomdConnection (AdomdConnection): For querying. See [AdomdConnection MS Docs](https://learn.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.adomdclient.adomdconnection?view=analysisservices-dotnet). Connection made from parts of the originally provided connection string.
            Tables (PyTables[PyTable]): Wrappers for [Table MS Docs](https://learn.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.tabular.table?view=analysisservices-dotnet). So you have the full capabilities of what the MS Docs offer and a few others. Like `Tabular().Tables['Table Name'].Row_Count()`. Or you can find a table via `Tabular().Tables[0]` or `Tabular().Tables['Table Name']`
            Columns (List[Column]): Easy access list of columns from model. See [Column MS Docs](https://learn.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.tabular.column?view=analysisservices-dotnet).
            Partitions (List[Partition]): Easy access list of partitions from model. See [Partition MS Docs](https://learn.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.partition?view=analysisservices-dotnet).
            Measures (List[Measure]): Easy access list of measures from model. See [Measure MS Docs](https://learn.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.tabular.table.measures?view=analysisservices-dotnet#microsoft-analysisservices-tabular-table-measures).
    """

    def __init__(self, connection_str: str):

        # Connecting to model...
        logger.debug("Initializing Tabular Class")
        self.Server = Server()
        self.Server.Connect(connection_str)
        logger.info(f"Connected to Server - {self.Server.Name}")
        self.Catalog = self.Server.ConnectionInfo.Catalog
        logger.debug(f"Received Catalog - {self.Catalog}")
        try:
            self.Database = [
                database
                for database in self.Server.Databases.GetEnumerator()
                if database.Name == self.Catalog or self.Catalog is None
            ][0]
        except Exception:
            err_msg = f"Unable to find Database... {self.Catalog}"
            logger.error(err_msg)
            raise Exception(err_msg)
        logger.info(f"Connected to Database - {self.Database.Name}")
        self.CompatibilityLevel: int = self.Database.CompatibilityLevel
        self.CompatibilityMode: int = self.Database.CompatibilityMode.value__
        self.Model = self.Database.Model
        logger.info(f"Connected to Model - {self.Model.Name}")
        self.Adomd: Connection = Connection(self.Server)
        self.Effective_Users: dict = {}
        self.PyRefresh = PyRefresh

        # Build PyObjects
        self.reload_model_info()

        # Run subclass init
        super().__init__(self.Model)

        # Building rich table display for repr
        self._display.add_row(
            "EstimatedSize",
            f"{round(self.Database.EstimatedSize / 1000000000, 2)} GB",
            end_section=True,
        )
        self._display.add_row("# of Tables", str(len(self.Tables)))
        self._display.add_row("# of Partitions", str(len(self.Partitions)))
        self._display.add_row("# of Columns", str(len(self.Columns)))
        self._display.add_row(
            "# of Measures", str(len(self.Measures)), end_section=True
        )
        self._display.add_row("Database", self.Database.Name)
        self._display.add_row("Server", self.Server.Name)

        # Finished and registering disconnect
        logger.debug("Class Initialization Completed")
        logger.debug("Registering Disconnect on Termination...")
        atexit.register(self.disconnect)

    def reload_model_info(self) -> bool:
        """Runs on __init__ iterates through details, can be called after any model changes. Called in save_changes()

        Returns:
                bool: True if successful
        """
        self.Database.Refresh()

        self.Tables = PyTables(
            [PyTable(table, self) for table in self.Model.Tables.GetEnumerator()]
        )
        self.Relationships = PyRelationships(
            [
                PyRelationship(relationship, self)
                for relationship in self.Model.Relationships.GetEnumerator()
            ]
        )
        self.Partitions = PyPartitions(
            [partition for table in self.Tables for partition in table.Partitions]
        )
        self.Columns = PyColumns(
            [column for table in self.Tables for column in table.Columns]
        )
        self.Measures = PyMeasures(
            [measure for table in self.Tables for measure in table.Measures]
        )

        self.Cultures = PyCultures(
            [
                PyCulture(culture, self)
                for culture in self.Model.Cultures.GetEnumerator()
            ]
        )
        return True

    def is_process(self) -> bool:
        """Run method to check if Processing is occurring. Will query DMV $SYSTEM.DISCOVER_JOBS to see if any processing is happening.

        Returns:
                bool: True if DMV shows Process, False if not.
        """
        _jobs_df = self.Query("select * from $SYSTEM.DISCOVER_JOBS")
        return len(_jobs_df[_jobs_df["JOB_DESCRIPTION"] == "Process"]) > 0

    def disconnect(self) -> None:
        """Disconnects from Model"""
        logger.info(f"Disconnecting from - {self.Server.Name}")
        atexit.unregister(self.disconnect)
        return self.Server.Disconnect()

    def reconnect(self) -> None:
        """Reconnects to Model"""
        logger.info(f"Reconnecting to {self.Server.Name}")
        return self.Server.Reconnect()

    def refresh(self, *args, **kwargs) -> pd.DataFrame:
        """PyRefresh Class to handle refreshes of model.

        Args:
            model (Tabular): Main Tabular Class
            object (Union[str, PyTable, PyPartition, Dict[str, Any]]): Designed to handle a few different ways of selecting a refresh. Can be a string of 'Table Name' or dict of {'Table Name': 'Partition Name'} or even some combination with the actual PyTable and PyPartition classes.
            trace (Base_Trace, optional): Set to `None` if no Tracing is desired, otherwise you can use default trace or create your own. Defaults to Refresh_Trace.
            refresh_checks (Refresh_Check_Collection, optional): Add your `Refresh_Check`'s into a `Refresh_Check_Collection`. Defaults to Refresh_Check_Collection().
            default_row_count_check (bool, optional): Quick built in check will fail the refresh if post check row count is zero. Defaults to True.
            refresh_type (RefreshType, optional): Input RefreshType desired. Defaults to RefreshType.Full.

        Returns:
            pd.DataFrame
        """
        return self.PyRefresh(self, *args, **kwargs).run()

    def save_changes(self):
        """Called after refreshes or any model changes.
        Currently will return a named tuple of all changes detected. However a ton of room for improvement here.
        """
        if self.Server.Connected is False:
            self.reconnect()

        def property_changes(property_changes_var):
            """
            Returns any property changes.
            """
            property_change = namedtuple(
                "property_change",
                "new_value object original_value property_name property_type",
            )
            return [
                property_change(
                    change.NewValue,
                    change.Object,
                    change.OriginalValue,
                    change.PropertyName,
                    change.PropertyType,
                )
                for change in property_changes_var.GetEnumerator()
            ]

        logger.info("Executing save_changes()...")
        model_save_results = self.Model.SaveChanges()
        if isinstance(model_save_results.Impact, type(None)):
            logger.warning(f"No changes detected on save for {self.Server.Name}")
            return None
        else:
            property_changes_var = model_save_results.Impact.PropertyChanges
            added_objects = model_save_results.Impact.AddedObjects
            added_subtree_roots = model_save_results.Impact.AddedSubtreeRoots
            removed_objects = model_save_results.Impact.RemovedObjects
            removed_subtree_roots = model_save_results.Impact.RemovedSubtreeRoots
            xmla_results = model_save_results.XmlaResults
            changes = namedtuple(
                "changes",
                "property_changes added_objects added_subtree_roots removed_objects removed_subtree_Roots xmla_results",
            )
            [
                property_changes(property_changes_var),
                added_objects,
                added_subtree_roots,
                removed_objects,
                removed_subtree_roots,
                xmla_results,
            ]
            self.reload_model_info()
            return changes(
                property_changes(property_changes_var),
                added_objects,
                added_subtree_roots,
                removed_objects,
                removed_subtree_roots,
                xmla_results,
            )

    def backup_table(self, table_str: str) -> bool:
        """Will be removed. This is experimental with no written pytest for it.
        Backs up table in memory, brings with it measures, columns, hierarchies, relationships, roles, etc.
        It will add suffix '_backup' to all objects.
        Refresh is performed from source during backup.

        Args:
                table_str (str, optional): Name of Table.

        Returns:
                bool: Returns True if Successful, else will return error.
        """
        logger.info("Backup Beginning...")
        logger.debug(f"Cloning {table_str}")
        table = self.Model.Tables.find(table_str).Clone()
        logger.info("Beginning Renames")

        def rename(items):
            """Iterates through items and requests rename."""
            for item in items:
                item.RequestRename(f"{item.Name}_backup")
                logger.debug(f"Renamed - {item.Name}")

        logger.info("Renaming Columns")
        rename(table.Columns.GetEnumerator())
        logger.info("Renaming Partitions")
        rename(table.Partitions.GetEnumerator())
        logger.info("Renaming Measures")
        rename(table.Measures.GetEnumerator())
        logger.info("Renaming Hierarchies")
        rename(table.Hierarchies.GetEnumerator())
        logger.info("Renaming Table")
        table.RequestRename(f"{table.Name}_backup")
        logger.info("Adding Table to Model as backup")
        self.Model.Tables.Add(table)
        logger.info("Finding Necessary Relationships... Cloning...")
        relationships = [
            relationship.Clone()
            for relationship in self.Model.Relationships.GetEnumerator()
            if relationship.ToTable.Name == remove_suffix(table.Name, "_backup")
            or relationship.FromTable.Name == remove_suffix(table.Name, "_backup")
        ]
        logger.info("Renaming Relationships")
        rename(relationships)
        logger.info("Switching Relationships to Clone Table & Column")
        for relationship in relationships:
            logger.debug(f"Renaming - {relationship.Name}")
            if relationship.ToTable.Name == remove_suffix(table.Name, "_backup"):
                relationship.set_ToColumn(
                    table.Columns.find(f"{relationship.ToColumn.Name}_backup")
                )
            elif relationship.FromTable.Name == remove_suffix(table.Name, "_backup"):
                relationship.set_FromColumn(
                    table.Columns.find(f"{relationship.FromColumn.Name}_backup")
                )
            logger.debug(f"Adding {relationship.Name} to {self.Model.Name}")
            self.Model.Relationships.Add(relationship)

        def clone_role_permissions():
            """Clones the role permissions for table."""
            logger.info("Beginning to handle roles and permissions for table...")
            logger.debug("Finding Roles...")
            roles = [
                role
                for role in self.Model.Roles.GetEnumerator()
                for tablepermission in role.TablePermissions.GetEnumerator()
                if tablepermission.Name == table_str
            ]
            for role in roles:
                logger.debug(f"Role {role.Name} matched, looking into it...")
                logger.debug("Searching for table specific permissions")
                tablepermissions = [
                    table.Clone()
                    for table in role.TablePermissions.GetEnumerator()
                    if table.Name == table_str
                ]
                for tablepermission in tablepermissions:
                    logger.debug(
                        f"{tablepermission.Name} found... switching table to clone"
                    )
                    tablepermission.set_Table(table)
                    for column in tablepermission.ColumnPermissions.GetEnumerator():
                        logger.debug(
                            f"Column - {column.Name} copying permissions to clone..."
                        )
                        column.set_Column(
                            self.Model.Tables.find(table.Name).Columns.find(
                                f"{column.Name}_backup"
                            )
                        )
                    logger.debug(f"Adding {tablepermission.Name} to {role.Name}")
                    role.TablePermissions.Add(tablepermission)
            return True

        clone_role_permissions()
        logger.info(f"Refreshing Clone... {table.Name}")
        self.reload_model_info()
        self.refresh(table.Name, default_row_count_check=False)
        logger.info(f"Updating Model {self.Model.Name}")
        self.save_changes()
        return True

    def revert_table(self, table_str: str) -> bool:
        """Will be removed. This is experimental with no written pytest for it. This is used in conjunction with Backup_Table().
        It will take the 'TableName_backup' and replace with the original.
        Example scenario ->
        1. model.Backup_Table('TableName')
        2. perform any proposed changes in original 'TableName'
        3. validate changes in 'TableName'
        4. if unsuccessful run model.Revert_Table('TableName')

        Args:
                table_str (str): Name of table.

        Returns:
                bool: Returns True if Successful, else will return error.
        """
        logger.info(f"Beginning Revert for {table_str}")
        logger.debug(f"Finding original {table_str}")
        main = self.Model.Tables.find(table_str)
        logger.debug(f"Finding backup {table_str}")
        backup = self.Model.Tables.find(f"{table_str}_backup")
        logger.debug("Finding original relationships")
        main_relationships = [
            relationship
            for relationship in self.Model.Relationships.GetEnumerator()
            if relationship.ToTable.Name == main.Name
            or relationship.FromTable.Name == main.Name
        ]
        logger.debug("Finding backup relationships")
        backup_relationships = [
            relationship
            for relationship in self.Model.Relationships.GetEnumerator()
            if relationship.ToTable.Name == backup.Name
            or relationship.FromTable.Name == backup.Name
        ]

        def remove_role_permissions():
            """
            Removes role permissions from table.
            """
            logger.debug(
                f"Finding table and column permission in roles to remove from {table_str}"
            )
            roles = [
                role
                for role in self.Model.Roles.GetEnumerator()
                for tablepermission in role.TablePermissions.GetEnumerator()
                if tablepermission.Name == table_str
            ]
            for role in roles:
                logger.debug(f"Role {role.Name} Found")
                tablepermissions = [
                    table
                    for table in role.TablePermissions.GetEnumerator()
                    if table.Name == table_str
                ]
                for tablepermission in tablepermissions:
                    logger.debug(f"Removing {tablepermission.Name} from {role.Name}")
                    role.TablePermissions.Remove(tablepermission)

        for relationship in main_relationships:
            logger.debug("Cleaning relationships...")
            if relationship.ToTable.Name == main.Name:
                logger.debug(f"Removing {relationship.Name}")
                self.Model.Relationships.Remove(relationship)
            elif relationship.FromTable.Name == main.Name:
                logger.debug(f"Removing {relationship.Name}")
                self.Model.Relationships.Remove(relationship)
        logger.debug(f"Removing Original Table {main.Name}")
        self.Model.Tables.Remove(main)
        remove_role_permissions()

        def dename(items):
            """
            Denames all items.
            """
            for item in items:
                logger.debug(f"Removing Suffix for {item.Name}")
                item.RequestRename(remove_suffix(item.Name, "_backup"))
                logger.debug(f"Saving Changes... for {item.Name}")
                self.Model.save_changes()

        logger.info("Name changes for Columns...")
        dename(
            [
                column
                for column in backup.Columns.GetEnumerator()
                if column.Type != ColumnType.RowNumber
            ]
        )
        logger.info("Name changes for Partitions...")
        dename(backup.Partitions.GetEnumerator())
        logger.info("Name changes for Measures...")
        dename(backup.Measures.GetEnumerator())
        logger.info("Name changes for Hierarchies...")
        dename(backup.Hierarchies.GetEnumerator())
        logger.info("Name changes for Relationships...")
        dename(backup_relationships)
        logger.info("Name changes for Backup Table...")
        backup.RequestRename(remove_suffix(backup.Name, "_backup"))
        self.save_changes()
        return True

    def query(
        self, query_str: str, effective_user: str = None
    ) -> Union[pd.DataFrame, str, int]:
        """Executes Query on Model and Returns Results in Pandas DataFrame

        Args:
                Query_Str (str): Dax Query. Note, needs full syntax (ex: EVALUATE). See (DAX Queries)[https://docs.microsoft.com/en-us/dax/dax-queries].
                Will check if query string is a file. If it is, then it will perform a query on whatever is read from the file.
                It is also possible to query DMV. For example. Query("select * from $SYSTEM.DISCOVER_TRACE_EVENT_CATEGORIES"). See (DMVs)[https://docs.microsoft.com/en-us/analysis-services/instances/use-dynamic-management-views-dmvs-to-monitor-analysis-services?view=asallproducts-allversions]
                Effective_User (str): User you wish to query as.

        Returns:
                pd.DataFrame: Returns dataframe with results
        """
        if effective_user is None:
            return self.Adomd.query(query_str)

        try:
            # This needs a public model with effective users to properly test
            conn = self.effective_users[effective_user]
            logger.debug(f"Effective user found querying as... {effective_user}")
        except Exception:
            logger.debug(f"Creating new connection with {effective_user}")
            conn = Connection(self.Server, effective_user=effective_user)
            self.effective_Users[effective_user] = conn

        return conn.query(query_str)

    def analyze_bpa(
        self, tabular_editor_exe: str, best_practice_analyzer: str
    ) -> List[str]:
        """Takes your Tabular Model and performs TE2s BPA. Runs through Command line.
        [Tabular Editor BPA](https://docs.tabulareditor.com/te2/Best-Practice-Analyzer.html)
        [Tabular Editor Command Line Options](https://docs.tabulareditor.com/te2/Command-line-Options.html)

        Args:
                tabular_editor_exe (str): TE2 Exe File path. Feel free to use class TE2().EXE_Path or provide your own.
                best_practice_analyzer (str): BPA json file path. Feel free to use class BPA().Location or provide your own. Defualts to 	https://raw.githubusercontent.com/microsoft/Analysis-Services/master/BestPracticeRules/BPARules.json

        Returns:
                List[str]: Assuming no failure, will return list of BPA violations. Else will return error from command line.
        """
        logger.debug("Beginning request to talk with TE2 & Find BPA...")
        bim_file_location = f"{os.getcwd()}\\Model.bim"
        atexit.register(remove_file, bim_file_location)
        cmd = f'{tabular_editor_exe} "Provider=MSOLAP;{self.Adomd.ConnectionString}" {self.Database.Name} -B "{bim_file_location}" -A {best_practice_analyzer} -V/?'
        logger.debug("Command Generated")
        logger.debug("Submitting Command...")
        sp = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        raw_output, error = sp.communicate()
        if len(error) > 0:
            return error
        else:
            return [
                output for output in raw_output.split("\n") if "violates rule" in output
            ]

    def create_table(self, df: pd.DataFrame, table_name: str) -> bool:
        """Creates tables from pd.DataFrame as an M-Partition.
        So will convert the dataframe to M-Partition logic via the M query table constructor.
        Runs refresh and will update model.

        Args:
                df (pd.DataFrame): DataFrame to add to model
                table_name (str): _description_

        Returns:
                bool: True if successful
        """
        logger.debug(f"Beginning to create table for {table_name}...")
        new_table = Table()
        new_table.RequestRename(table_name)
        logger.debug("Sorting through columns...")
        df_column_names = df.columns
        dtype_conversion = pandas_datatype_to_tabular_datatype(df)
        for df_column_name in df_column_names:
            logger.debug(f"Adding {df_column_name} to Table...")
            column = DataColumn()
            column.RequestRename(df_column_name)
            column.set_SourceColumn(df_column_name)
            column.set_DataType(dtype_conversion[df_column_name])
            new_table.Columns.Add(column)
        logger.debug("Expression String Created...")
        logger.debug("Creating MPartition...")
        partition = Partition()
        partition.set_Source(MPartitionSource())
        logger.debug("Setting MPartition Expression...")
        partition.Source.set_Expression(pd_dataframe_to_m_expression(df))
        logger.debug(
            f"Adding partition: {partition.Name} to {self.Server.Name}::{self.Database.Name}::{self.Model.Name}"
        )
        new_table.Partitions.Add(partition)
        logger.debug(
            f"Adding table: {new_table.Name} to {self.Server.Name}::{self.Database.Name}::{self.Model.Name}"
        )
        self.Model.Tables.Add(new_table)
        self.save_changes()
        self.reload_model_info()
        self.refresh(new_table.Name)
        return True
