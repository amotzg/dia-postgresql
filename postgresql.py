import os.path
import time

import dia

DIA_TABLE_FIRST_FIELD_CONN = 12

DIA_MESSAGE_NOTICE = 0
DIA_MESSAGE_WARNING = 1
DIA_MESSAGE_ERROR = 2  # Can be any number other than 0 and 1.

TABLE_TYPE_NAME = 'Database - Table'


class SQLRenderer(object):
    def __init__(self):
        self._sql_file = None

    def begin_render(self, data, filename):
        self._sql_file = open(filename, "w")
        layer = data.active_layer
        pgsql = PostgreSql(os.path.basename(filename))
        # pgsql = PostgreSql(get_members(dia.active_display(), ",\n"))
        tables = {}
        refs = []
        for obj in layer.objects:
            if obj.type.name == TABLE_TYPE_NAME:
                t = DiaTable(obj)
                tables[t.name()] = t
            elif obj.type.name == 'Database - Reference':
                # TODO check all cases of unconnected refs.
                r = DiaReference(obj)
                ref_table = r.table_name()
                src_table = r.ref_table()
                if ref_table:
                    if src_table:
                        tables[ref_table].add_ref(r)
                    else:
                        dia.message(DIA_MESSAGE_WARNING, "Disconnected reference to %s." % ref_table)

                else:
                    if src_table:
                        dia.message(DIA_MESSAGE_WARNING, "Disconnected reference from %s." % src_table)
                    else:
                        dia.message(DIA_MESSAGE_WARNING, "Diagram contains disconnected reference.")
                refs.append(r)
            elif obj.type.name == 'Database - Compound':
                ac = DiaAttrCompound(obj)
                ac_table_names = ac.table_names()
                if None in ac_table_names:
                    dia.message(DIA_MESSAGE_WARNING, "Disconnected compound %s." % ac_table_names)
                elif ac_table_names.count(ac_table_names[0]) != len(ac_table_names):
                    dia.message(DIA_MESSAGE_WARNING, "Compound connected to more than one table %s." % ac_table_names)
                else:
                    # Assume only one primary key. Might consider adding verification that no key was set previously.
                    tables[ac_table_names[0]].set_multi_column_key(ac)
            else:
                dia.message(DIA_MESSAGE_WARNING, "Unknown type: %s" % obj.type.name)
                # pgsql.unknown_object(obj)
        pgsql.drop_tables(tables.keys())
        for tbl in tables.values():
            pgsql.create_table_sql(tbl)
        pgsql.create_references_sql(refs)
        pgsql.write_sql(self._sql_file)

    def end_render(self):
        self._sql_file.close()


class DiaTable(object):
    def __init__(self, obj):
        self._obj = obj
        self._refs = []
        self._multi_col = None

    def name(self):
        return DH.dia_table_name(self._obj)

    def comment(self):
        return self._obj.properties['comment'].value
        # TODO consider using the visible_comment indicator

    def columns(self):
        return [DiaColumn(col) for col in self._obj.properties['attributes'].value]

    def connections(self, prefix, postfix):
        connected = ""
        for cpoint in self._obj.connections:
            if cpoint.connected:
                connected += prefix + cpoint.object.properties['name'].value + postfix

        return connected

    def handles(self, prefix, postfix):
        handles_members = ""
        for hndl in self._obj.handles:
            if hndl.connected_to is not None:
                handles_members += prefix + get_members(hndl) + postfix
        return handles_members

    def add_ref(self, ref):
        self._refs.append(ref)

    def set_multi_column_key(self, attr_comp):
        self._multi_col = attr_comp

    def references(self):
        return self._refs

    def multi_column_key(self):
        if self._multi_col is None:
            return None
        return self._multi_col.field_names()


class DiaColumn(object):
    def __init__(self, col):
        self._col = col

    def name(self):
        return self._col[0]

    def type_name(self):
        return self._col[1]

    def comment(self):
        return self._col[2]

    def is_primary(self):
        return self._col[3] == 1

    def is_nullable(self):
        return self._col[4] == 1

    def is_unique(self):
        return self._col[5] == 1

    def default_value(self):
        return self._col[6]


class DiaReference(object):
    def __init__(self, obj):
        self._obj = obj
        self._disconnected = None

    def table_name(self):
        tbl_cpoint = self._end_hndl_cpoint()
        if not tbl_cpoint:
            return None
        return DH.dia_table_name(tbl_cpoint.object)

    def foreign_key(self):
        tbl_cpoint = self._end_hndl_cpoint()
        if not tbl_cpoint:
            return None
        return DH.get_conn_field(tbl_cpoint)

    def ref_table(self):
        tbl_cpoint = self._start_hndl_cpoint()
        if not tbl_cpoint:
            return None
        return DH.dia_table_name(tbl_cpoint.object)

    def ref_field(self):
        tbl_cpoint = self._start_hndl_cpoint()
        if not tbl_cpoint:
            return None
        return DH.get_conn_field(tbl_cpoint)

    # obj.properties['start_point_desc'].value,

    def is_one2one(self):
        return 1 == self._obj.properties['end_point_desc'].value

    def on_delete(self):
        # TODO find delete/update policy representation
        return "RESTRICT"

    def _end_hndl_cpoint(self):
        return self._obj.handles[1].connected_to

    def _start_hndl_cpoint(self):
        return self._obj.handles[0].connected_to


class DiaAttrCompound(object):
    def __init__(self, obj):
        self._obj = obj
        # _obj.handles contain also center elbow handles, look only on table connected handles.
        self._cpoints = [hndl.connected_to for hndl in self._obj.handles if hndl.connect_type == 2]

    def table_names(self):
        return [DH.dia_table_name(cpoint.object) if cpoint else None for cpoint in self._cpoints]

    def field_names(self):
        return [DH.get_conn_field(cpoint) if cpoint else None for cpoint in self._cpoints]


# Helpers for dia object manipulations
class DH(object):
    @staticmethod
    def get_conn_field(cpoint):
        tbl = cpoint.object
        for i in range(len(tbl.connections)):
            if tbl.connections[i] == cpoint:
                break
        # The given cpoint should be of a known connection, so the next checks should be useless. But it wouldn't hurt
        else:
            return None
        if i is None:
            return None
        field_idx = (i - DIA_TABLE_FIRST_FIELD_CONN) / 2  # Each field line, has 2 connections, left and right.
        idx = 0
        idxname = ""
        for att in tbl.properties.get("attributes").value:
            if idx == field_idx:
                idxname = att[0]
                break
            idx += 1

        return idxname

    @staticmethod
    def dia_table_name(obj):
        if obj.type.name == TABLE_TYPE_NAME:
            return obj.properties['name'].value
        return None


class PostgreSql(object):
    def __init__(self,  file_name):
        # self._sql = "-- Generated from %s\n" % file_name
        # self._sql += "-- %s\n\n" % time.strftime("%d/%m/%Y %H:%M")
        self._sql = "\n-- Generated at %s\n\n" % time.strftime("%d/%m/%Y %H:%M")

    def write_sql(self, f):
        f.write(self._sql)

    def unknown_object(self, obj):
        self._sql += "Unknown type: %s\n\t" % obj.type.name
        self._sql += get_members(obj, "\n\t")
        self._sql += enum_props(obj)
        self._sql += "\n\n"

    def drop_tables(self, table_names):
        for tname in table_names:
            self._sql += "DROP TABLE IF EXISTS " + tname + " CASCADE;\n"
        self._sql += "\n"

    def create_table_sql(self, table):
        if table.comment():
            self._sql += "-- %s\n" % table.comment()
        self._sql += "CREATE TABLE " + table.name() + " (\n"
        longest_col_name = reduce(lambda longest, col: max(longest, len(col.name())), table.columns(), 0)
        multi_key = table.multi_column_key()
        previous_primary = None
        table_lines = []
        for col in table.columns():
            col_line = ""
            if col.comment():
                col_line += "\t-- %s\n" % col.comment()
            col_line += "\t%-*s\t%s\t" % (longest_col_name, col.name(), col.type_name())
            if col.is_primary() and not multi_key:
                if previous_primary:
                    dia.message(DIA_MESSAGE_WARNING,
                                "Multiple keys with no compound definition. Previous %s current %s." % (
                                    repr(previous_primary), repr(col.name()))
                                )
                previous_primary = col.name()
                col_line += "PRIMARY KEY "
            else:
                if col.is_unique():
                    col_line += "UNIQUE "
                if not col.is_nullable():
                    col_line += "NOT NULL "
            if col.default_value():
                col_line += "DEFAULT %s " % col.default_value()
            table_lines.append(col_line)
        if multi_key:
            table_lines.append("\tPRIMARY KEY (%s)" % (", ".join(multi_key)))
        self._sql += ",\n".join(table_lines)
        self._sql += "\n);\n\n"

    def create_references_sql(self, refs):
        ref_lines = []
        for ref in refs:
            tbl_name = ref.table_name()
            ref_tbl_name = ref.ref_table()
            if tbl_name and ref_tbl_name:
                ref_lines.append("ALTER TABLE ONLY %s ADD FOREIGN KEY (%s) REFERENCES %s (%s)" % (
                    tbl_name,
                    ref.foreign_key(),
                    ref_tbl_name,
                    ref.ref_field()
                ))
        # ON DELETE RESTRICT
        # ON DELETE CASCADE,
        # NO ACTION
        # SET NULL and SET DEFAULT
        self._sql += ";\n".join(ref_lines)
        self._sql += ";\n\n"


def get_members(obj, sep=", "):
    members = []
    for a in dir(obj):
        if not a.startswith('__'):
            memb = str(a)
            try:
                attr_val = getattr(obj, a)
            except AttributeError:
                pass
            else:
                if callable(attr_val):
                    memb = memb + "()"
                else:
                    memb = memb + "=" + str(attr_val)
            members.append(memb)
    return sep.join(members)


def enum_props(obj):
    prop_string = ""
    for prop_key in obj.properties.keys():
        prop_string += "%s:\n" % prop_key
        prop = obj.properties[prop_key]
        prop_string += "\t%s, %s, %s, %s\n" % (prop.name, prop.type, prop.value, prop.visible)
    return prop_string


dia.register_export("Generate PostgreSQL create script", "sql", SQLRenderer())
