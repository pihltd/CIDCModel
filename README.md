# CIDCModel
Work on CIDC model
# Scripts
## CIDC2MDF.py
A script that reads an Excel spreadsheet of the CIDC model and writes out the MDF compliant file(s).  Requires a YAML configuration file\
### Usage
python CIDC2MDF -c /<configfile/> -v /<verbose output/>\
### Config file options
 - *workingpath* (String): Path to where MDF files will be written and input Excel files is saved
 - *excelfile* (String): The name of the input Excel file
 - *worksheet* (String): The worksheet name containing the nodes, properties, PVs, etc.
 - *mdffile* (String): Name of the output model file.  This will contain any remaining information if separate files are used.
 - *separate_files* (Boolean): If True, separate files will be writting for each node listed in *mdffiles*.  If False, all output will be to *mdffile*
 - *mdffiles* (List of Dictionary):  This is a list of dictionaries with the MDF Section as the key, and the file name as the value.  Valid keys include PropDefiintions, Term, Relationsihps, Terms, Nodes, Handle, Version, Tags.  Any MDF sections not specified here will be printed out to the file specified in *mdffile*\
 *Example*: (PropDefinitions: 'My_model_properties.yml') will create a *My_model_properties.yml* file containing all the entries under PropDefinitions, and all remaining MDF sections in hte *mdffile*.
