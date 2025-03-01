from __future__ import annotations
import pickle
from table import Table
from time import sleep, localtime, strftime
import os,sys
from btree import Btree
import shutil
from misc import split_condition
import logging
import warnings
import readline
from tabulate import tabulate


# sys.setrecursionlimit(100)

# Clear command cache (journal)
readline.clear_history()

class Database:
    '''
    Main Database class, containing tables.
    '''

    def __init__(self, name, load=True):
        self.tables = {}
        self._name = name

        self.savedir = f'dbdata/{name}_db'

        if load:
            try:
                self.load_database()
                logging.info(f'Loaded "{name}".')
                return
            except:
                warnings.warn(f'Database "{name}" does not exist. Creating new.')

        # create dbdata directory if it doesnt exist
        if not os.path.exists('dbdata'):
            os.mkdir('dbdata')

        # create new dbs save directory
        try:
            os.mkdir(self.savedir)
        except:
            pass

        # create all the meta tables
        self.create_table('meta_length', 'table_name,no_of_rows', 'str,int')
        self.create_table('meta_locks', 'table_name,pid,mode', 'str,int,str')
        self.create_table('meta_insert_stack', 'table_name,indexes', 'str,list')
        self.create_table('meta_indexes', 'table_name,index_name', 'str,str')
        self.save_database()

    def save_database(self):
        '''
        Save database as a pkl file. This method saves the database object, including all tables and attributes.
        '''
        for name, table in self.tables.items():
            with open(f'{self.savedir}/{name}.pkl', 'wb') as f:
                pickle.dump(table, f)

    def _save_locks(self):
        '''
        Stores the meta_locks table to file as meta_locks.pkl.
        '''
        with open(f'{self.savedir}/meta_locks.pkl', 'wb') as f:
            pickle.dump(self.tables['meta_locks'], f)

    def load_database(self):
        '''
        Load all tables that are part of the database (indices noted here are loaded).

        Args:
            path: string. Directory (path) of the database on the system.
        '''
        path = f'dbdata/{self._name}_db'
        for file in os.listdir(path):

            if file[-3:]!='pkl': # if used to load only pkl files
                continue
            f = open(path+'/'+file, 'rb')
            tmp_dict = pickle.load(f)
            f.close()
            name = f'{file.split(".")[0]}'
            self.tables.update({name: tmp_dict})
            # setattr(self, name, self.tables[name])

    #### IO ####

    def _update(self):
        '''
        Update all meta tables.
        '''
        self._update_meta_length()
        self._update_meta_insert_stack()


    def create_table(self, name, column_names, column_types, primary_key=None, foreign_key=None, ref=None, load=None):
        '''
        This method create a new table. This table is saved and can be accessed via db_object.tables['table_name'] or db_object.table_name

        Args:
            name: string. Name of table.
            column_names: list. Names of columns.
            column_types: list. Types of columns.
            primary_key: string. The primary key (if it exists).
            foreign_key: list. Name of foreign key columns (or foreign key cause there might be only one).
            ref: list. Contains name of parent table followed by the primary key column of the parent table.
            load: boolean. Defines table object parameters as the name of the table and the column names.
        '''

        if foreign_key != None and ref != None:
            for i in range(len(ref)):

                # check if index of loop is an even number
                # we need that cause in ref in each "even" index
                # we have stored the referenced table
                # and in each "odd" index we have stored
                # each refernced column of that table
                if i % 2 == 0:
                    
                    # check if the referenced tables exist
                    if not ref[i] in self.tables:
                        print(f'ERROR: Cannot create table {name}\n')
                        print(f'Referenced table {ref[i]} does not exist! \n')
                        return

                else:

                    # check if column names are part of a table
                    if not ref[i] in self.tables.get(ref[i-1]).column_names:
                        print(f'ERROR: Column {ref[i]} doesn\'t exist in table {ref[i-1]}')
                        return

                    # check if given referenced column is the pk (in the future we should also check if the column is unique)
                    # of the given referenced table
                    if self.tables.get(ref[i-1]).pk != ref[i]:
                        print(f'ERROR: Column {ref[i]} is not a pk of table {ref[i-1]}')
                        return

        # print('here -> ', column_names.split(','))
        self.tables.update({name: Table(name=name, column_names=column_names.split(','), column_types=column_types.split(','), primary_key=primary_key, foreign_key=foreign_key, ref=ref, load=load)})
        # self._name = Table(name=name, column_names=column_names, column_types=column_types, load=load)
        # check that new dynamic var doesnt exist already
        # self.no_of_tables += 1
        self._update()
        self.save_database()
        # (self.tables[name])
        print(f'Created table "{name}".')


    def drop_table(self, table_name):
        '''
        Drop table from current database.

        Args:
            table_name: string. Name of table.
        '''
        self.load_database()
        self.lock_table(table_name)

        self.tables.pop(table_name)
        if os.path.isfile(f'{self.savedir}/{table_name}.pkl'):
            os.remove(f'{self.savedir}/{table_name}.pkl')
        else:
            warnings.warn(f'"{self.savedir}/{table_name}.pkl" not found.')
        self.delete_from('meta_locks', f'table_name={table_name}')
        self.delete_from('meta_length', f'table_name={table_name}')
        self.delete_from('meta_insert_stack', f'table_name={table_name}')

        # self._update()
        self.save_database()


    def import_table(self, table_name, filename, column_types=None, primary_key=None):
        '''
        Creates table from CSV file.

        Args:
            filename: string. CSV filename. If not specified, filename's name will be used.
            column_types: list. Types of columns. If not specified, all will be set to type str.
            primary_key: string. The primary key (if it exists).
        '''
        file = open(filename, 'r')

        first_line=True
        for line in file.readlines():
            if first_line:
                colnames = line.strip('\n')
                if column_types is None:
                    column_types = ",".join(['str' for _ in colnames.split(',')])
                self.create_table(name=table_name, column_names=colnames, column_types=column_types, primary_key=primary_key)
                lock_ownership = self.lock_table(table_name, mode='x')
                first_line = False
                continue
            self.tables[table_name]._insert(line.strip('\n').split(','))

        if lock_ownership:
             self.unlock_table(table_name)
        self._update()
        self.save_database()


    def export(self, table_name, filename=None):
        '''
        Transform table to CSV.

        Args:
            table_name: string. Name of table.
            filename: string. Output CSV filename.
        '''
        res = ''
        for row in [self.tables[table_name].column_names]+self.tables[table_name].data:
            res+=str(row)[1:-1].replace('\'', '').replace('"','').replace(' ','')+'\n'

        if filename is None:
            filename = f'{table_name}.csv'

        with open(filename, 'w') as file:
           file.write(res)

    def table_from_object(self, new_table):
        '''
        Add table object to database.

        Args:
            new_table: string. Name of new table.
        '''

        self.tables.update({new_table._name: new_table})
        if new_table._name not in self.__dir__():
            setattr(self, new_table._name, new_table)
        else:
            raise Exception(f'"{new_table._name}" attribute already exists in class "{self.__class__.__name__}".')
        self._update()
        self.save_database()



    ##### table functions #####

    # In every table function a load command is executed to fetch the most recent table.
    # In every table function, we first check whether the table is locked. Since we have implemented
    # only the X lock, if the tables is locked we always abort.
    # After every table function, we update and save. Update updates all the meta tables and save saves all
    # tables.

    # these function calls are named close to the ones in postgres

    def cast(self, column_name, table_name, cast_type):
        '''
        Modify the type of the specified column and cast all prexisting values.
        (Executes type() for every value in column and saves)

        Args:
            table_name: string. Name of table (must be part of database).
            column_name: string. The column that will be casted (must be part of database).
            cast_type: type. Cast type (do not encapsulate in quotes).
        '''
        self.load_database()
        
        lock_ownership = self.lock_table(table_name, mode='x')
        self.tables[table_name]._cast_column(column_name, eval(cast_type))
        if lock_ownership:
            self.unlock_table(table_name)
        self._update()
        self.save_database()

    def insert_into(self, table_name, row_str):
        '''
        Inserts data to given table.

        Args:
            table_name: string. Name of table (must be part of database).
            row: list. A list of values to be inserted (will be casted to a predifined type automatically).
            lock_load_save: boolean. If False, user needs to load, lock and save the states of the database (CAUTION). Useful for bulk-loading.
        '''
        row = row_str.strip().split(',')
        self.load_database()
        # fetch the insert_stack. For more info on the insert_stack
        # check the insert_stack meta table
        lock_ownership = self.lock_table(table_name, mode='x')
        insert_stack = self._get_insert_stack_for_table(table_name)
        try:

            # case where we are trying to insert values in a table that has a foreign key
            if self.tables[table_name].fk_idx != None:

                found = False # flag that indicates if we found the value that going to be inserted on the parent table pk

                parent_table = self.tables[table_name].ref_table # get the parent table of the current one
                for j in range(len(self.tables[parent_table].data)):

                    # check if the row contains a value that is not in the primary key column of the parent table
                    if int(row[self.tables[parent_table].pk_idx]) == int(self.tables[parent_table].data[j][0]):
                        found = True # if there is update the flag

                if found:
                    self.tables[table_name]._insert(row, insert_stack)
                else:
                    print(f'ERROR: Cannot add row: a foreign key constraint fails')
                    print(f'Value {int(row[self.tables[parent_table].pk_idx])} not found in the referenced column of parent table {parent_table}')

            else:
                # this is the base case in which there are no foreign keys
                self.tables[table_name]._insert(row, insert_stack)

        except Exception as e:
            logging.info(e)
            logging.info('ABORTED')
        self._update_meta_insert_stack_for_tb(table_name, insert_stack[:-1])

        if lock_ownership:
            self.unlock_table(table_name)
        self._update()
        self.save_database()


    def update_table(self, table_name, set_args, condition):
        '''
        Update the value of a column where a condition is met.

        Args:
            table_name: string. Name of table (must be part of database).
            set_value: string. New value of the predifined column name.
            set_column: string. The column to be altered.
            condition: string. A condition using the following format:
                'column[<,<=,==,>=,>]value' or
                'value[<,<=,==,>=,>]column'.
                
                Operatores supported: (<,<=,==,>=,>)
        '''
        set_column, set_value = set_args.replace(' ','').split('=')
        self.load_database()
        
        lock_ownership = self.lock_table(table_name, mode='x')
        self.tables[table_name]._update_rows(set_value, set_column, condition)
        if lock_ownership:
            self.unlock_table(table_name)
        self._update()
        self.save_database()

    def delete_from(self, table_name, condition):
        '''
        Delete rows of table where condition is met.

        Args:
            table_name: string. Name of table (must be part of database).
            condition: string. A condition using the following format:
                'column[<,<=,==,>=,>]value' or
                'value[<,<=,==,>=,>]column'.
                
                Operatores supported: (<,<=,==,>=,>)
        '''
        self.load_database()
        
        lock_ownership = self.lock_table(table_name, mode='x')
        deleted = self.tables[table_name]._delete_where(condition)
        if lock_ownership:
            self.unlock_table(table_name)
        self._update()
        self.save_database()
        # we need the save above to avoid loading the old database that still contains the deleted elements
        if table_name[:4]!='meta':
            self._add_to_insert_stack(table_name, deleted)
        self.save_database()

    def select(self, columns, table_name, condition, order_by=None, top_k=True,\
               desc=None, save_as=None, return_object=True):
        '''
        Selects and outputs a table's data where condtion is met.

        Args:
            table_name: string. Name of table (must be part of database).
            columns: list. The columns that will be part of the output table (use '*' to select all available columns)
            condition: string. A condition using the following format:
                'column[<,<=,==,>=,>]value' or
                'value[<,<=,==,>=,>]column'.
                
                Operatores supported: (<,<=,==,>=,>)
            order_by: string. A column name that signals that the resulting table should be ordered based on it (no order if None).
            desc: boolean. If True, order_by will return results in descending order (True by default).
            top_k: int. An integer that defines the number of rows that will be returned (all rows if None).
            save_as: string. The name that will be used to save the resulting table into the database (no save if None).
            return_object: boolean. If True, the result will be a table object (useful for internal use - the result will be printed by default).
        '''
        # print(table_name)
        self.load_database()
        if isinstance(table_name,Table):
            return table_name._select_where(columns, condition, order_by, desc, top_k)

        if condition is not None:
            condition_column = split_condition(condition)[0]
        else:
            condition_column = ''

        
        # self.lock_table(table_name, mode='x')
        if self.is_locked(table_name):
            return
        if self._has_index(table_name) and condition_column==self.tables[table_name].column_names[self.tables[table_name].pk_idx]:
            index_name = self.select('*', 'meta_indexes', f'table_name={table_name}', return_object=True).column_by_name('index_name')[0]
            bt = self._load_idx(index_name)
            table = self.tables[table_name]._select_where_with_btree(columns, bt, condition, order_by, desc, top_k)
        else:
            table = self.tables[table_name]._select_where(columns, condition, order_by, desc, top_k)
        # self.unlock_table(table_name)
        if save_as is not None:
            table._name = save_as
            self.table_from_object(table)
        else:
            if return_object:
                return table
            else:
                return table.show()


    def show_table(self, table_name, no_of_rows=None):
        '''
        Print table in a readable tabular design (using tabulate).

        Args:
            table_name: string. Name of table (must be part of database).
        '''
        self.load_database()
        
        self.tables[table_name].show(no_of_rows, self.is_locked(table_name))


    def sort(self, table_name, column_name, asc=False):
        '''
        Sorts a table based on a column.

        Args:
            table_name: string. Name of table (must be part of database).
            column_name: string. the column name that will be used to sort.
            asc: If True sort will return results in ascending order (False by default).
        '''

        self.load_database()
        
        lock_ownership = self.lock_table(table_name, mode='x')
        self.tables[table_name]._sort(column_name, asc=asc)
        if lock_ownership:
            self.unlock_table(table_name)
        self._update()
        self.save_database()

    def evaluate_join_method(self, left_table, right_table, condition):
        '''
        Based on some varius factors return the proper Join method to be used.

        Args:
            left_table: Table. Table object supplied in the querry before the different join types.
            right_table: Table. Table object supplied in the querry after the different join types.
            condition: string. A condition using the following format:
                'column[<,<=,==,>=,>]value' or
                'value[<,<=,==,>=,>]column'.
        '''

        if (condition=='=' and left_table.pk==None and right_table.pk==None):
            return 'SMJ'

        if(left_table.pk==None and right_table.pk!=None):
            return 'INLJ'
        else:
            return 'NLJ'


    def inlj(self, left_table, table_right, condition):
        '''
        Implementation of the Index Nested Loop Join algorithm. For this to work we need the right table 
        to have an index (and for that we need to have a primary key).

        Args:
            left_table: Table. Table object supplied in the querry before the different join types.
            right_table: Table. Table object supplied in the querry after the different join types.
            condition: string. A condition using the following format:
                'column[<,<=,==,>=,>]value' or
                'value[<,<=,==,>=,>]column'.
        '''

        if (table_right.pk != None):
            # get columns and operator
            column_name_left, operator, column_name_right = left_table._parse_condition(condition, join=True)
            # try to find both columns, if you fail raise error
            try:
                column_index_left = left_table.column_names.index(column_name_left)
            except:
                raise Exception(f'Column "{column_name_left}" dont exist in left table. Valid columns: {left_table.column_names}.')

            try:
                column_index_right = table_right.column_names.index(column_name_right)
            except:
                raise Exception(f'Column "{column_name_right}" dont exist in right table. Valid columns: {table_right.column_names}.')

            # get the column names of both tables with the table name in front
            # ex. for left -> name becomes left_table_name_name etc
            left_names = [f'{left_table._name}.{colname}' if left_table._name!='' else colname for colname in left_table.column_names]
            right_names = [f'{table_right._name}.{colname}' if table_right._name!='' else colname for colname in table_right.column_names]

            # define the new tables name, its column names and types
            join_table_name = ''
            join_table_colnames = left_names+right_names
            join_table_coltypes = left_table.column_types+table_right.column_types
            join_table = Table(name=join_table_name, column_names=join_table_colnames, column_types= join_table_coltypes)

            if not(self._has_index(table_right._name)): #if it does not have an index:
                #create index using the name of the right table
                self.create_index(table_right._name, table_right._name)
                pass
            
            # get that index
            idx = self._load_idx(table_right._name)
           
            #inlj algorithm
            for row in left_table.data:
                value = row[column_index_left]
                res = idx.find('=',value)
                if len(res) > 0: #if there is a common value, the length will be > 0
                    for i in res:
                        join_table._insert(row + table_right.data[i]) #populate the join_table with the results

            return join_table

    def smj(self, left_table, right_table, condition):
        '''
        Implementation of the Sort-Merge Join algorithm. Merges two sorted tables into one and returns it.

        Args:
            left_table: Table. Table object supplied in the querry before the different join types.
            right_table: Table. Table object supplied in the querry after the different join types.
            condition: string. A condition using the following format:
                'column[<,<=,==,>=,>]value' or
                'value[<,<=,==,>=,>]column'.
        '''


        # get columns and operator
        column_name_left, operator, column_name_right = left_table._parse_condition(condition, join=True)
        # try to find both columns, if you fail raise error
        try:
            column_index_left = left_table.column_names.index(column_name_left)
        except:
            raise Exception(f'Column "{column_name_left}" dont exist in left table. Valid columns: {left_table.column_names}.')

        try:
            column_index_right = right_table.column_names.index(column_name_right)
        except:
            raise Exception(f'Column "{column_name_right}" dont exist in right table. Valid columns: {right_table.column_names}.')

        # get the column names of both tables with the table name in front
        # ex. for left -> name becomes left_table_name_name etc
        left_names = [f'{left_table._name}.{colname}' if left_table._name!='' else colname for colname in left_table.column_names]
        right_names = [f'{right_table._name}.{colname}' if right_table._name!='' else colname for colname in right_table.column_names]

        # define the new tables name, its column names and types
        join_table_name = ''
        join_table_colnames = left_names+right_names
        join_table_coltypes = left_table.column_types+right_table.column_types
        join_table = Table(name=join_table_name, column_names=join_table_colnames, column_types= join_table_coltypes)

        # check if both tables are sorted
        # if not left_table.is_sorted():
        #     # left_table.e_merge_sort()
        #     pass

        # if not left_table.is_sorted():
        #     # right_table.e_merge_sort()
        #     pass

        left_table_length = len(left_table.data)
        right_table_length = len(right_table.data)

        i = 0
        j = 0
        first_occurrence = 0 # track the first occurrence of a value

        while (i < left_table_length and j < right_table_length):
            
            # when the value of the left table is smaller then just go to the next values
            # there is no point checking the rest of the right table cause they are sorted
            # so we will never encounter a smaller value again
            if (left_table.data[i][column_index_left] < right_table.data[j][column_index_right]):
                i += 1
                
            # the same logic applies when the right value of is smaller than the left one
            elif (left_table.data[i][column_index_left] > right_table.data[j][column_index_right]):
                j += 1

            else:
                # if they are equal merge that data and insert it to the table
                join_table._insert(left_table.data[i] + right_table.data[j])

                # when the current element is different than the previus element then 
                # this is the first time we find it, thus we save it in 'first_occurrence'
                if(right_table.data[j - 1][column_index_right] != right_table.data[j][column_index_right]):
                    first_occurrence = j
                
                # if the current index + 1 is out of bounds of the right table's length, then reset the index to the first occurrence of that element.
                # else continue normally
                if(j + 1 > right_table_length):
                    i += 1
                    j = first_occurrence
                else:
                    j += 1
        
        return join_table


    def join(self, mode, left_table, right_table, condition, save_as=None, return_object=True):
        '''
        Join two tables that are part of the database where condition is met.

        Args:
            left_table: string. Name of the left table (must be in DB) or Table obj.
            right_table: string. Name of the right table (must be in DB) or Table obj.
            condition: string. A condition using the following format:
                'column[<,<=,==,>=,>]value' or
                'value[<,<=,==,>=,>]column'.
                
                Operatores supported: (<,<=,==,>=,>)
        save_as: string. The output filename that will be used to save the resulting table in the database (won't save if None).
        return_object: boolean. If True, the result will be a table object (useful for internal usage - the result will be printed by default).
        '''
        self.load_database()
        if self.is_locked(left_table) or self.is_locked(right_table):
            return

        left_table = left_table if isinstance(left_table, Table) else self.tables[left_table] 
        right_table = right_table if isinstance(right_table, Table) else self.tables[right_table] 

        if mode=='inner':
            
            method = self.evaluate_join_method(left_table, right_table, condition)
            if method == 'SMJ':
                print(f'Using SMJ')
                res = self.smj(left_table, right_table, condition)
            elif method == 'INLJ':
                print(f'Using INLJ')
                res = self.inlj(left_table, right_table, condition)
            else:
                res = left_table._inner_join(right_table, condition)


        else:
            raise NotImplementedError

        if save_as is not None:
            res._name = save_as
            self.table_from_object(res)
        else:
            if return_object:
                return res
            else:
                res.show()

    def lock_table(self, table_name, mode='x'):
        '''
        Locks the specified table using the exclusive lock (X).

        Args:
            table_name: string. Table name (must be part of database).
        '''
        if table_name[:4]=='meta' or table_name not in self.tables.keys() or isinstance(table_name,Table):
            return

        with open(f'{self.savedir}/meta_locks.pkl', 'rb') as f:
            self.tables.update({'meta_locks': pickle.load(f)})

        try:
            pid = self.tables['meta_locks']._select_where('pid',f'table_name={table_name}').data[0][0]
            if pid!=os.getpid():
                raise Exception(f'Table "{table_name}" is locked by process with pid={pid}')
            else:
                return False

        except IndexError:
            pass

        if mode=='x':
            self.tables['meta_locks']._insert([table_name, os.getpid(), mode])
        else:
            raise NotImplementedError
        self._save_locks()
        return True
        # print(f'Locking table "{table_name}"')

    def unlock_table(self, table_name, force=False):
        '''
        Unlocks the specified table that is exclusively locked (X).

        Args:
            table_name: string. Table name (must be part of database).
        '''
        if table_name not in self.tables.keys():
            raise Exception(f'Table "{table_name}" is not in database')

        if not force:
            try:
                # pid = self.select('*','meta_locks',  f'table_name={table_name}', return_object=True).data[0][1]
                pid = self.tables['meta_locks']._select_where('pid',f'table_name={table_name}').data[0][0]
                if pid!=os.getpid():
                    raise Exception(f'Table "{table_name}" is locked by the process with pid={pid}')
            except IndexError:
                pass
        self.tables['meta_locks']._delete_where(f'table_name={table_name}')
        self._save_locks()
        # print(f'Unlocking table "{table_name}"')

    def is_locked(self, table_name):
        '''
        Check whether the specified table is exclusively locked (X).

        Args:
            table_name: string. Table name (must be part of database).
        '''
        if isinstance(table_name,Table) or table_name[:4]=='meta':  # meta tables will never be locked (they are internal)
            return False

        with open(f'{self.savedir}/meta_locks.pkl', 'rb') as f:
            self.tables.update({'meta_locks': pickle.load(f)})

        try:
            pid = self.tables['meta_locks']._select_where('pid',f'table_name={table_name}').data[0][0]
            if pid!=os.getpid():
                raise Exception(f'Table "{table_name}" is locked by the process with pid={pid}')

        except IndexError:
            pass
        return False

    def journal(idx = None):
        if idx != None:
            cache_list = '\n'.join([str(readline.get_history_item(i + 1)) for i in range(readline.get_current_history_length())]).split('\n')[int(idx)]
            out = tabulate({"Command": cache_list.split('\n')}, headers=["Command"])
        else:
            cache_list = '\n'.join([str(readline.get_history_item(i + 1)) for i in range(readline.get_current_history_length())])
            out = tabulate({"Command": cache_list.split('\n')}, headers=["Index","Command"], showindex="always")
        print('journal:', out)
        #return out


    #### META ####

    # The following functions are used to update, alter, load and save the meta tables.
    # Important: Meta tables contain info regarding the NON meta tables ONLY.
    # i.e. meta_length will not show the number of rows in meta_locks etc.

    def _update_meta_length(self):
        '''
        Updates the meta_length table.
        '''
        for table in self.tables.values():
            if table._name[:4]=='meta': #skip meta tables
                continue
            if table._name not in self.tables['meta_length'].column_by_name('table_name'): # if new table, add record with 0 no. of rows
                self.tables['meta_length']._insert([table._name, 0])

            # the result needs to represent the rows that contain data. Since we use an insert_stack
            # some rows are filled with Nones. We skip these rows.
            non_none_rows = len([row for row in table.data if any(row)])
            self.tables['meta_length']._update_rows(non_none_rows, 'no_of_rows', f'table_name={table._name}')
            # self.update_row('meta_length', len(table.data), 'no_of_rows', 'table_name', '==', table._name)

    def _update_meta_locks(self):
        '''
        Updates the meta_locks table.
        '''
        for table in self.tables.values():
            if table._name[:4]=='meta': #skip meta tables
                continue
            if table._name not in self.tables['meta_locks'].column_by_name('table_name'):

                self.tables['meta_locks']._insert([table._name, False])
                # self.insert('meta_locks', [table._name, False])

    def _update_meta_insert_stack(self):
        '''
        Updates the meta_insert_stack table.
        '''
        for table in self.tables.values():
            if table._name[:4]=='meta': #skip meta tables
                continue
            if table._name not in self.tables['meta_insert_stack'].column_by_name('table_name'):
                self.tables['meta_insert_stack']._insert([table._name, []])


    def _add_to_insert_stack(self, table_name, indexes):
        '''
        Adds provided indices to the insert stack of the specified table.

        Args:
            table_name: string. Table name (must be part of database).
            indexes: list. The list of indices that will be added to the insert stack (the indices of the newly deleted elements).
        '''
        old_lst = self._get_insert_stack_for_table(table_name)
        self._update_meta_insert_stack_for_tb(table_name, old_lst+indexes)

    def _get_insert_stack_for_table(self, table_name):
        '''
        Returns the insert stack of the specified table.

        Args:
            table_name: string. Table name (must be part of database).
        '''
        return self.tables['meta_insert_stack']._select_where('*', f'table_name={table_name}').column_by_name('indexes')[0]
        # res = self.select('meta_insert_stack', '*', f'table_name={table_name}', return_object=True).indexes[0]
        # return res

    def _update_meta_insert_stack_for_tb(self, table_name, new_stack):
        '''
        Replaces the insert stack of a table with the one supplied by the user.

        Args:
            table_name: string. Table name (must be part of database).
            new_stack: string. The stack that will be used to replace the existing one.
        '''
        self.tables['meta_insert_stack']._update_rows(new_stack, 'indexes', f'table_name={table_name}')


    # indexes
    def create_index(self, index_name, table_name, index_type='btree'):
        '''
        Creates an index on a specified table with a given name.
        Important: An index can only be created on a primary key (the user does not specify the column).

        Args:
            table_name: string. Table name (must be part of database).
            index_name: string. Name of the created index.
        '''
        if self.tables[table_name].pk_idx is None: # if no primary key, no index
            raise Exception('Cannot create index. Table has no primary key.')
        if index_name not in self.tables['meta_indexes'].column_by_name('index_name'):
            # currently only btree is supported. This can be changed by adding another if.
            if index_type=='btree':
                logging.info('Creating Btree index.')
                # insert a record with the name of the index and the table on which it's created to the meta_indexes table
                self.tables['meta_indexes']._insert([table_name, index_name])
                # crate the actual index
                self._construct_index(table_name, index_name)
                self.save_database()
        else:
            raise Exception('Cannot create index. Another index with the same name already exists.')

    def _construct_index(self, table_name, index_name):
        '''
        Construct a btree on a table and save.

        Args:
            table_name: string. Table name (must be part of database).
            index_name: string. Name of the created index.
        '''
        bt = Btree(3) # 3 is arbitrary

        # for each record in the primary key of the table, insert its value and index to the btree
        for idx, key in enumerate(self.tables[table_name].column_by_name(self.tables[table_name].pk)):
            bt.insert(key, idx)
        # save the btree
        self._save_index(index_name, bt)


    def _has_index(self, table_name):
        '''
        Check whether the specified table's primary key column is indexed.

        Args:
            table_name: string. Table name (must be part of database).
        '''
        return table_name in self.tables['meta_indexes'].column_by_name('table_name')

    def _save_index(self, index_name, index):
        '''
        Save the index object.

        Args:
            index_name: string. Name of the created index.
            index: obj. The actual index object (btree object).
        '''
        try:
            os.mkdir(f'{self.savedir}/indexes')
        except:
            pass

        with open(f'{self.savedir}/indexes/meta_{index_name}_index.pkl', 'wb') as f:
            pickle.dump(index, f)

    def _load_idx(self, index_name):
        '''
        Load and return the specified index.

        Args:
            index_name: string. Name of created index.
        '''
        f = open(f'{self.savedir}/indexes/meta_{index_name}_index.pkl', 'rb')
        index = pickle.load(f)
        f.close()
        return index