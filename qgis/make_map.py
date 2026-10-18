"""Build the QA map project and PNG. Run with the QGIS python:
    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" qgis\\make_map.py
"""
import os
import re
import sys
import zipfile
from pathlib import Path

# stable xml attribute order
os.environ["QT_HASH_SEED"] = "0"

from qgis.core import (
    Qgis, QgsApplication, QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem,
    QgsDataSourceUri, QgsFillSymbol, QgsHueSaturationFilter, QgsLineSymbol, QgsMarkerSymbol, QgsLayoutExporter, QgsLayoutItemLabel, QgsLayoutItemLegend,
    QgsLayoutItemMap, QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize,
    QgsPalLayerSettings, QgsPrintLayout, QgsProject, QgsProperty, QgsRasterLayer,
    QgsRendererCategory, QgsRuleBasedRenderer, QgsSymbol, QgsSymbolLayer,
    QgsTextFormat, QgsUnitTypes, QgsVectorLayer, QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QFont

ROOT = Path(__file__).resolve().parent.parent
PROJECT_FILE = ROOT / "qgis" / "qa_map.qgz"
IMAGE_FILE = ROOT / "documentation" / "qa_map.png"

# check name, legend label, color, marker shape
CHECK_STYLE = [
    ("osm_hifld_disagreement", "OSM and HIFLD disagree", "#d7191c", Qgis.MarkerShape.Diamond),
    ("possible_mapping_gap", "possible mapping gap", "#fd8d3c", Qgis.MarkerShape.Square),
    ("support_not_on_line", "pole or tower not on a line", "#7b3294", Qgis.MarkerShape.Triangle),
    ("voltage_disagreement", "voltage disagrees with HIFLD", "#008837", Qgis.MarkerShape.Star),
    ("missing_voltage", "missing voltage", "#525252", Qgis.MarkerShape.Circle),
    ("missing_operator", "missing operator", "#bdbdbd", Qgis.MarkerShape.Circle),
]


def read_env():
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def pg_layer(env, table, name):
    uri = QgsDataSourceUri()
    uri.setConnection(env["PGHOST"], env["PGPORT"], env["PGDATABASE"], env["PGUSER"], env["PGPASSWORD"])
    uri.setDataSource("public", table, "geom")
    layer = QgsVectorLayer(uri.uri(False), name, "postgres")
    if not layer.isValid():
        sys.exit(f"could not open table {table}, is the database running?")
    fixed_profile_colors(layer)
    return layer


def fixed_profile_colors(layer):
    # profile symbols default to random colors
    profile = layer.elevationProperties()
    profile.setProfileLineSymbol(QgsLineSymbol.createSimple({"line_color": "128,128,128"}))
    profile.setProfileFillSymbol(QgsFillSymbol.createSimple({"color": "128,128,128"}))
    if hasattr(profile, "setProfileMarkerSymbol"):
        profile.setProfileMarkerSymbol(QgsMarkerSymbol.createSimple({"color": "128,128,128"}))


def style_flood(layer):
    root = QgsRuleBasedRenderer.Rule(None)
    for label, expr, color in [
        ("FEMA high risk flood zone", "\"sfha_tf\" = 'T'", "#2b8cbe"),
        ("FEMA 0.2% annual chance zone", "\"zone_subty\" ILIKE '0.2 PCT%'", "#a6bddb"),
    ]:
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(QColor(color))
        symbol.setOpacity(0.45)
        symbol.symbolLayer(0).setStrokeStyle(0)
        root.appendChild(QgsRuleBasedRenderer.Rule(symbol, filterExp=expr, label=label))
    layer.setRenderer(QgsRuleBasedRenderer(root))


def style_line(layer, color, width, opacity=1.0):
    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    symbol.setColor(QColor(color))
    symbol.setWidth(width)
    layer.renderer().setSymbol(symbol)
    layer.setOpacity(opacity)


def style_findings(layer):
    categories = []
    for check, label, color, shape in CHECK_STYLE:
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(QColor(color))
        marker = symbol.symbolLayer(0)
        marker.setShape(shape)
        # bigger in sfha zones
        marker.setDataDefinedProperty(
            QgsSymbolLayer.Property.Size,
            QgsProperty.fromExpression("CASE WHEN \"flood_rank\" = 1 THEN 4.5 ELSE 2.6 END"))
        categories.append(QgsRendererCategory(check, symbol, label))
    layer.setRenderer(QgsCategorizedSymbolRenderer("check_name", categories))

    # label the top 10
    settings = QgsPalLayerSettings()
    settings.fieldName = "CASE WHEN \"priority\" <= 10 THEN \"priority\" END"
    settings.isExpression = True
    text = QgsTextFormat()
    text.setFont(QFont("Arial", 9, QFont.Bold))
    text.setSize(9)
    text.buffer().setEnabled(True)
    settings.setFormat(text)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def build_project(project, env):
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:2278"))
    project.styleSettings().setRandomizeDefaultSymbolColor(False)
    basemap = QgsRasterLayer(
        "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0",
        "basemap", "wms")
    basemap.hueSaturationFilter().setGrayscaleMode(QgsHueSaturationFilter.GrayscaleLightness)
    basemap.setOpacity(0.45)
    fixed_profile_colors(basemap)
    flood = pg_layer(env, "flood_zones", "FEMA flood zones")
    hifld = pg_layer(env, "hifld_lines", "HIFLD transmission lines")
    osm = pg_layer(env, "osm_lines", "OSM power lines")
    findings = pg_layer(env, "ranked_errors", "QA findings")
    study = pg_layer(env, "study_area", "study area")

    style_flood(flood)
    style_line(hifld, "#e31a1c", 1.4, opacity=0.6)
    style_line(osm, "#252525", 0.5)
    style_findings(findings)

    for layer in (basemap, flood, hifld, osm, findings):
        project.addMapLayer(layer)
    return study.extent()


def text_format(size, bold=False):
    fmt = QgsTextFormat()
    fmt.setFont(QFont("Arial", size, QFont.Bold if bold else QFont.Normal))
    fmt.setSize(size)
    return fmt


def export_png(project, extent):
    mm = QgsUnitTypes.LayoutMillimeters
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.pageCollection().page(0).setPageSize(QgsLayoutSize(297, 230, mm))

    title = QgsLayoutItemLabel(layout)
    title.setText("Houston power grid GIS QA findings, ranked by flood risk")
    title.setTextFormat(text_format(14, bold=True))
    title.attemptMove(QgsLayoutPoint(8, 5, mm))
    title.attemptResize(QgsLayoutSize(280, 10, mm))
    layout.addLayoutItem(title)

    map_item = QgsLayoutItemMap(layout)
    map_item.attemptMove(QgsLayoutPoint(8, 16, mm))
    map_item.attemptResize(QgsLayoutSize(205, 205, mm))
    map_item.setCrs(QgsCoordinateReferenceSystem("EPSG:2278"))
    map_item.zoomToExtent(extent)
    layout.addLayoutItem(map_item)

    legend = QgsLayoutItemLegend(layout)
    legend.setLinkedMap(map_item)
    legend.setAutoUpdateModel(False)
    legend.setTitle("Legend")
    legend.model().rootGroup().removeLayer(project.mapLayersByName("basemap")[0])
    legend.attemptMove(QgsLayoutPoint(216, 16, mm))
    layout.addLayoutItem(legend)

    scale = QgsLayoutItemScaleBar(layout)
    scale.setLinkedMap(map_item)
    scale.setStyle("Single Box")
    scale.applyDefaultSize(QgsUnitTypes.DistanceMiles)
    scale.attemptMove(QgsLayoutPoint(12, 208, mm))
    layout.addLayoutItem(scale)

    note = QgsLayoutItemLabel(layout)
    note.setText("Large symbols are in a FEMA high risk flood zone.\n"
                 "Numbers are the top 10 priorities.\n\n"
                 "Data: OpenStreetMap contributors (ODbL), HIFLD, FEMA NFHL.\n"
                 "Basemap: OpenStreetMap, shown in gray.\n"
                 "Coordinates: EPSG:2278, US feet.")
    note.setTextFormat(text_format(7))
    note.attemptMove(QgsLayoutPoint(216, 180, mm))
    note.attemptResize(QgsLayoutSize(76, 40, mm))
    layout.addLayoutItem(note)

    # exportToImage gives a gdal error on png
    image = QgsLayoutExporter(layout).renderPageToImage(0, QSize(), 150)
    if image.isNull() or not image.save(str(IMAGE_FILE), "PNG"):
        sys.exit("map export failed")


def clean_project_file(qgz_path, password, private_words):
    with zipfile.ZipFile(qgz_path) as z:
        qgs_name = next(n for n in z.namelist() if n.endswith(".qgs"))
        qgs = z.read(qgs_name)

    qgs = re.sub(rb" password='[^']*'", b"", qgs)
    qgs = re.sub(rb' (saveUser|saveUserFull|saveDateTime)="[^"]*"', b"", qgs)
    qgs = re.sub(rb"<author>[^<]*</author>", b"<author></author>", qgs)
    qgs = re.sub(rb"<creation>[^<]*</creation>", b"<creation></creation>", qgs)
    qgs = re.sub(rb'\s*<date type="Created" value="[^"]*"/>', b"", qgs)
    # zero the uuid part of layer ids
    qgs = re.sub(rb"_[0-9a-f]{8}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{12}",
                 b"_00000000_0000_0000_0000_000000000000", qgs)
    qgs = re.sub(rb'projectStyleId="[^"]*"', b'projectStyleId=""', qgs)
    # stable symbol ids
    numbered = {}
    qgs = re.sub(
        rb"\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}",
        lambda m: numbered.setdefault(m.group(0), b"{00000000-0000-0000-0000-%012d}" % len(numbered)),
        qgs)
    # snapping settings are unordered
    qgs = re.sub(rb"((?:[ \t]*<layer-setting [^>]*/>\r?\n)+)",
                 lambda m: b"".join(sorted(m.group(1).splitlines(keepends=True))), qgs)

    for word in [password, *private_words]:
        if word and word.encode() in qgs:
            sys.exit("private text is still in the project file, not saving it")

    # drop the empty style db
    info = zipfile.ZipInfo(qgs_name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(qgz_path, "w") as z:
        z.writestr(info, qgs)


def main():
    app = QgsApplication([], False)
    app.initQgis()
    env = read_env()
    project = QgsProject.instance()

    extent = build_project(project, env)
    export_png(project, extent)
    print(f"saved {IMAGE_FILE}")

    project.write(str(PROJECT_FILE))
    private = [os.environ.get("USERNAME", ""), QgsApplication.userFullName()]
    clean_project_file(PROJECT_FILE, env["PGPASSWORD"], private)
    print(f"saved {PROJECT_FILE} without the password or user name")
    app.exitQgis()


if __name__ == "__main__":
    main()
