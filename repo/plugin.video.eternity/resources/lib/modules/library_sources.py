# -*- coding: utf-8 -*-
"""
    Eternity Add-on - Library Sources Module

    Manages Kodi video sources integration:
    - Adds library folders to Kodi sources.xml
    - Sets content type and scraper for folders
    - Updates MyVideos database
"""

import xml.etree.ElementTree as ET
from resources.lib.modules.control import transPath, existsPath


def add_source(source_name, source_path, source_content, source_thumbnail, type='video'):
    """
    Add source to Kodi sources.xml and set content/scraper

    Args:
        source_name: Name shown in Kodi (e.g. "Eternity Movies")
        source_path: Physical path to library folder
        source_content: SQL INSERT statement for MyVideos DB (scraper config)
        source_thumbnail: Icon path
        type: Source type ('video', 'music', 'programs', etc.)
    """
    xml_file = transPath('special://profile/sources.xml')

    # Create sources.xml if it doesn't exist
    if not existsPath(xml_file):
        with open(xml_file, 'w') as f:
            f.write(
'''<sources>
	<programs>
		<default pathversion="1"/>
	</programs>
	<video>
		<default pathversion="1"/>
	</video>
	<music>
		<default pathversion="1"/>
	</music>
	<pictures>
		<default pathversion="1"/>
	</pictures>
	<files>
		<default pathversion="1"/>
	</files>
	<games>
		<default pathversion="1"/>
	</games>
</sources>
''')

    # Check if source already exists
    existing_source = _get_source_attr(xml_file, source_name, 'path', type=type)

    # If source exists but path changed, remove old content
    if existing_source and existing_source != source_path and source_content != '':
        _remove_source_content(existing_source)

    # Add/update source in XML
    if _add_source_xml(xml_file, source_name, source_path, source_thumbnail, type=type) and source_content != '':
        # Remove any old content (from manual deletions)
        _remove_source_content(source_path)
        # Set new content/scraper
        _set_source_content(source_content)


def _add_source_xml(xml_file, name, path, thumbnail, type='video'):
    """Add or update source in sources.xml"""
    tree = ET.parse(xml_file)
    root = tree.getroot()
    sources = root.find(type)

    existing_source = None

    # Find existing source by name or path
    for source in sources.findall('source'):
        xml_name = source.find('name').text
        xml_path = source.find('path').text
        if source.find('thumbnail') is not None:
            xml_thumbnail = source.find('thumbnail').text
        else:
            xml_thumbnail = ''

        if xml_name == name or xml_path == path:
            existing_source = source
            break

    if existing_source is not None:
        # Source exists - check if update needed
        xml_name = source.find('name').text
        xml_path = source.find('path').text
        if source.find('thumbnail') is not None:
            xml_thumbnail = source.find('thumbnail').text
        else:
            xml_thumbnail = ''

        if xml_name == name and xml_path == path and xml_thumbnail == thumbnail:
            # No changes needed
            return False
        elif xml_name == name:
            # Update path and thumbnail
            source.find('path').text = path
            source.find('thumbnail').text = thumbnail
        elif xml_path == path:
            # Update name and thumbnail
            source.find('name').text = name
            source.find('thumbnail').text = thumbnail
        else:
            # Update all
            source.find('path').text = path
            source.find('name').text = name
    else:
        # Create new source
        new_source = ET.SubElement(sources, 'source')
        new_name = ET.SubElement(new_source, 'name')
        new_name.text = name
        new_path = ET.SubElement(new_source, 'path')
        new_thumbnail = ET.SubElement(new_source, 'thumbnail')
        new_allowsharing = ET.SubElement(new_source, 'allowsharing')
        new_path.attrib['pathversion'] = '1'
        new_thumbnail.attrib['pathversion'] = '1'
        new_path.text = path
        new_thumbnail.text = thumbnail
        new_allowsharing.text = 'true'

    # Format XML with indentation
    _indent_xml(root)
    tree.write(xml_file)
    return True


def _indent_xml(elem, level=0):
    """Format XML with proper indentation"""
    i = '\n' + level*'\t'
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + '\t'
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            _indent_xml(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def _get_source_attr(xml_file, name, attr, type='video'):
    """Get attribute value from source by name"""
    tree = ET.parse(xml_file)
    root = tree.getroot()
    sources = root.find(type)
    for source in sources.findall('source'):
        xml_name = source.find('name').text
        if xml_name == name:
            return source.find(attr).text
    return None


def _db_execute(db_name, command):
    """Execute SQL command on Kodi database"""
    databaseFile = _get_database(db_name)
    if not databaseFile:
        return False

    from sqlite3 import dbapi2
    dbcon = dbapi2.connect(databaseFile)
    dbcur = dbcon.cursor()
    dbcur.execute(command)
    dbcon.commit()
    dbcur.close()
    dbcon.close()
    return True


def _get_database(db_name):
    """Find Kodi database file (supports wildcards like MyVideos*.db)"""
    from glob import glob
    path_db = 'special://profile/Database/%s' % db_name
    filelist = glob(transPath(path_db))
    if filelist:
        return filelist[-1]
    return None


def _remove_source_content(path):
    """Remove source content from MyVideos database"""
    q = 'DELETE FROM path WHERE strPath LIKE "%%{0}%%"'.format(path)
    return _db_execute('MyVideos*.db', q)


def _set_source_content(content):
    """Set source content in MyVideos database (scraper config)"""
    q = 'INSERT OR REPLACE INTO path (strPath,strContent,strScraper,strHash,scanRecursive,useFolderNames,strSettings,noUpdate,exclude,dateAdded,idParentPath) VALUES '
    q += content
    return _db_execute('MyVideos*.db', q)
