import logging
from object import PyObject
import pandas as pd
from partition import PyPartition, PyPartitions
from column import PyColumn, PyColumns
from measure import PyMeasure, PyMeasures
from pytabular.object import PyObjects
from logic_utils import ticks_to_datetime
from datetime import datetime

logger = logging.getLogger("PyTabular")


class PyTable(PyObject):
    """Wrapper for [Microsoft.AnalysisServices.Tabular.Table](https://learn.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.tabular.table?view=analysisservices-dotnet).
    With a few other bells and whistles added to it. You can use the table to access the nested Columns and Partitions. WIP

    Attributes:
        Model: Reference to Tabular class
        Partitions: Reference to Table Partitions
        Columns: Reference to Table Columns
    """

    def __init__(self, object, model) -> None:
        super().__init__(object)
        self.Model = model
        self.Partitions = PyPartitions(
            [
                PyPartition(partition, self)
                for partition in self._object.Partitions.GetEnumerator()
            ]
        )
        self.Columns = PyColumns(
            [PyColumn(column, self) for column in self._object.Columns.GetEnumerator()]
        )
        self.Measures = PyMeasures(
            [
                PyMeasure(measure, self)
                for measure in self._object.Measures.GetEnumerator()
            ]
        )
        self._display.add_row("# of Partitions", str(len(self.Partitions)))
        self._display.add_row("# of Columns", str(len(self.Columns)))
        self._display.add_row(
            "# of Measures", str(len(self.Measures)), end_section=True
        )
        self._display.add_row("Description", self._object.Description, end_section=True)
        self._display.add_row("DataCategory", str(self._object.DataCategory))
        self._display.add_row("IsHidden", str(self._object.IsHidden))
        self._display.add_row("IsPrivate", str(self._object.IsPrivate))
        self._display.add_row(
            "ModifiedTime",
            ticks_to_datetime(self._object.ModifiedTime.Ticks).strftime(
                "%m/%d/%Y, %H:%M:%S"
            ),
        )

    def Row_Count(self) -> int:
        """Method to return count of rows. Simple Dax Query:
        `EVALUATE {COUNTROWS('Table Name')}`

        Returns:
            int: Number of rows using [COUNTROWS](https://learn.microsoft.com/en-us/dax/countrows-function-dax).
        """
        return self.Model.Adomd.Query(f"EVALUATE {{COUNTROWS('{self.Name}')}}")

    def Refresh(self, *args, **kwargs) -> pd.DataFrame:
        """Same method from Model Refresh, you can pass through any extra parameters. For example:
        `Tabular().Tables['Table Name'].Refresh(Tracing = True)`
        Returns:
            pd.DataFrame: Returns pandas dataframe with some refresh details
        """
        return self.Model.Refresh(self, *args, **kwargs)

    def Last_Refresh(self) -> datetime:
        """Will query each partition for the last refresh time then select the max

        Returns:
            datetime: Last refresh time in datetime format
        """
        partition_refreshes = [
            partition.Last_Refresh() for partition in self.Partitions
        ]
        return max(partition_refreshes)

    def Related(self):
        return self.Model.Relationships.Related(self)


class PyTables(PyObjects):
    """Iterator to handle tables. Accessible via `Tables` attribute in Tabular class.

    Args:
        PyTable: PyTable class
    """

    def __init__(self, objects) -> None:
        super().__init__(objects)

    def Refresh(self, *args, **kwargs):
        model = self._objects[0].Model
        return model.Refresh(self, *args, **kwargs)

    def Query_All(self, query_function: str = "COUNTROWS(_)") -> pd.DataFrame:
        """This will dynamically create a query to pull all tables from the model and run the query function.
        It will replace the _ with the table to run.

        Args:
                query_function (str, optional): Dax query is dynamically building a query with the UNION & ROW DAX Functions. Defaults to 'COUNTROWS(_)'.

        Returns:
                pd.DataFrame: Returns dataframe with results
        """
        logger.info("Querying every table in PyTables...")
        logger.debug(f"Function to be run: {query_function}")
        logger.debug("Dynamically creating DAX query...")
        query_str = "EVALUATE UNION(\n"
        for table in self:
            table_name = table.get_Name()
            dax_table_identifier = f"'{table_name}'"
            query_str += f"ROW(\"Table\",\"{table_name}\",\"{query_function}\",{query_function.replace('_',dax_table_identifier)}),\n"
        query_str = f"{query_str[:-2]})"
        return self[0].Model.Query(query_str)

    def Find_Zero_Rows(self):
        """Returns PyTables class of tables with zero rows queried."""
        query_function: str = "COUNTROWS(_)"
        df = self.Query_All(query_function)

        table_names = df[df[f"[{query_function}]"].isna()]["[Table]"].to_list()
        logger.debug(f"Found {table_names}")
        tables = [self[name] for name in table_names]
        return self.__class__(tables)

    def Last_Refresh(self, group_partition: bool = True) -> pd.DataFrame:
        """Returns pd.DataFrame of tables with their latest refresh time.
        Optional 'group_partition' variable, default is True.
        If False an extra column will be include to have the last refresh time to the grain of the partition
        Example to add to model model.Create_Table(p.Table_Last_Refresh_Times(model),'RefreshTimes')

        Args:
                model (pytabular.Tabular): Tabular Model
                group_partition (bool, optional): Whether or not you want the grain of the dataframe to be by table or by partition. Defaults to True.

        Returns:
                pd.DataFrame: pd dataframe with the RefreshedTime property: https://docs.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.tabular.partition.refreshedtime?view=analysisservices-dotnet#microsoft-analysisservices-tabular-partition-refreshedtime
                If group_partition == True and the table has multiple partitions, then df.groupby(by["tables"]).max()
        """
        data = {
            "Tables": [
                partition.Table.Name for table in self for partition in table.Partitions
            ],
            "Partitions": [
                partition.Name for table in self for partition in table.Partitions
            ],
            "RefreshedTime": [
                partition.Last_Refresh()
                for table in self
                for partition in table.Partitions
            ],
        }
        df = pd.DataFrame(data)
        if group_partition:
            logger.debug("Grouping together to grain of Table")
            return (
                df[["Tables", "RefreshedTime"]]
                .groupby(by=["Tables"])
                .max()
                .reset_index(drop=False)
            )
        else:
            logger.debug("Returning DF")
            return df
