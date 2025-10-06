# https://github.com/CBIIT/bento-meta/blob/master/python/src/bento_meta/model.py
import pandas as pd
import numpy as np
import argparse
from crdclib import crdclib
from bento_meta.model import Model, Node, Property, Term, Edge
from bento_mdf import MDFWriter
import yaml
import json



def cleanColumnNames(oldnamelist):
    # The column names have a .1 appended and that causes trouble, so removing
    newcolumnnames = {}
    for oldname in oldnamelist:
        newname = oldname.split('.')[0]
        newcolumnnames[oldname] = newname
    return newcolumnnames


def cleanEnums(startlist):
    # The PV list in the spreadsheet is an unholy mess of characters.  Removing offenders and leading/trailing spaces
    cleaned = None
    if startlist is not None:
        removelist = ["'", "[", "]", '"']
        cleaned = []
        for entry in startlist:
            for remove in removelist:
                entry = entry.replace(remove, '')
            entry = entry.strip()
            cleaned.append(entry)
    return cleaned

def addNodes(datamodel, nodelist):
    # Add a list of nodes to the model
    for node in nodelist:
        nodeobj = Node({'handle': node})
        datamodel.add_node(nodeobj)
    return datamodel

def addEnums(propname, df):
    # Returns a list of permissible values
    enumlist = None
    enum_df = df.query('Property == @propname')
    for index, row in enum_df.iterrows():
        if row['Permissible Value'] not in ['-', np.nan]:
            enumlist = row['Permissible Value'].split(',')
    enumlist = cleanEnums(enumlist)
    return enumlist



def addProp(datamodel, df, nodelist):
    # Adds properties to the model.  Will add PVs if present
    for nodename in nodelist:
        working_df = df.query('Node == @nodename')
        for index, row in working_df.iterrows():
            propname = row['Property']
            datatype = row['Data Type']
            nodes = datamodel.nodes
            existing = list(nodes[nodename].props.keys())
            #Only add a new property if it's not there
            if propname not in existing:
                enumset = addEnums(propname, working_df)
                nodeobj = datamodel.nodes[nodename]
                if enumset is not None:
                    propdict = {'handle': propname, "_parent_handle": nodename, 'is_required': 'No', 'value_domain': 'value_set'}
                else:
                    propdict = {'handle': propname, "_parent_handle": nodename, 'is_required': 'No', 'value_domain': datatype}
                propobj = Property(propdict)
                
                datamodel.add_prop(nodeobj, propobj)
                if enumset is not None:
                    workingprop = datamodel.props[(nodename, propname)]
                    datamodel.add_terms(workingprop, *enumset)
    return datamodel

def addEnum(datamodel, df):
    # Not being used
    proplist = datamodel.props
    for prop in proplist:
        print(prop)
        nodename = prop[0]
        propname = prop[1]
        temp_df = df.query('Property == @propname')
        for index, row in temp_df.iterrows():
            if row['Permissible Value'] not in ['-', np.nan]:
                messylist = row['Permissible Value'].split(',')
                addprop = datamodel.props[(nodename,propname)]
                datamodel.add_terms(addprop, *messylist)
    return datamodel



def addTerm(datamodel, df):
    # Adds terms to a Property.  Currently not used
    proplist = df['Property'].unique()
    # This is a stupid safety valve because some rows are multi-mapped and therefore terms are duplicated.
    checkit = []
    for propname in proplist:
        term_df = df.query('Property == @propname')
        for index, row in term_df.iterrows():
            nodename = row['Node']
            cdename = 'NA'
            cdever = 'NA'
            cdeid = 'NA'
            description = 'None'
            cdeurl = 'None'
            if row['Permissible Value'] not in ['-', np.nan]:
                # These are an unholy mess, only thing to do is split on a comma
                messylist = row['Permissible Value'].split(',')
                termvalues = {'handle': propname, 'Enum': messylist}
                termobj = Term(termvalues)
                propobj = datamodel.props[(nodename, propname)]
                datamodel.add_terms(propobj, termobj)
    return datamodel



def writeFiles(mdf, configs):
    # This writes out the separate mode, property, etc., if reuested in the config.
    jsonobj = json.dumps(MDFWriter(mdf).mdf)
    mdfdict = json.loads(jsonobj)

    for entry in configs['mdffiles']:
        for mdfsection, filename in entry.items():
            printnode = {}
            printnode[mdfsection] = mdfdict.pop(mdfsection, None)
            crdclib.writeYAML(configs['workingpath']+filename, printnode)
    #After printing out the requested sections, print out what's left
    crdclib.writeYAML(configs['workingpath']+configs['mdffile'], mdfdict)





def main(args):
    # Read the config file
    configs = crdclib.readYAML(args.configfile)
    # Create a dataframe from the Excel sheet
    cidc_df = pd.read_excel(configs['workingpath']+configs['excelfile'], sheet_name=configs['worksheet'], usecols="G:K", header=8)

    # The header names are problematic, rename
    newcols = cleanColumnNames(cidc_df.columns.to_list())
    cidc_df.rename(columns=newcols, inplace=True)

    # Get the list of nodes
    cidc_nodes = cidc_df['Node'].unique().tolist()
    # Clean out a couple of bad values
    cidc_nodes.remove('-')
    cidc_nodes.remove(np.nan)


    # Create an empty model
    cidc_mdf = Model(handle='CIDC', version='0.01')

    # Add nodes
    cidc_mdf = addNodes(cidc_mdf, cidc_nodes)
    # Add properties and Enums
    cidc_mdf = addProp(cidc_mdf, cidc_df, cidc_nodes)
    # Add terms
    #cidc_df = addTerm(cidc_mdf, cidc_df)
    # Add Enums:
    # cidc_mdf = addEnum(cidc_mdf, cidc_df)

    #Attempt to write da model
    if configs['separate_files']:
        writeFiles(cidc_mdf, configs)
    else:
        filename = configs['workingpath']+configs['mdffile']
        with open(filename, "w") as f:
            f.write(yaml.dump(MDFWriter(cidc_mdf).mdf, indent=4))
        f.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--configfile", required=True,  help="Configuration file containing all the input info")
    parser.add_argument('-v', '--verbose', action='count', default=0, help=("Verbosity: -v main section -vv subroutine messages -vvv data returned shown"))

    args = parser.parse_args()

    main(args)

