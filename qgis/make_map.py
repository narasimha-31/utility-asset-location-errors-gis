"""Build the QA map project and PNG. Run with the QGIS python:
    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" qgis\\make_map.py
"""
import re
import sys
import zipfile
from pathlib import Path

from qgis.core import (
    Qgis, QgsApplication, QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem,
    QgsDataSourceUri, QgsHueSaturationFilter, QgsLayoutExporter, QgsLayoutItemLabel, QgsLayoutItemLegend,
    QgsLayoutItemMap, QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize,
    QgsPalLayerSettings, QgsPrintLayout, QgsProject, QgsProperty, QgsRasterLayer,
    QgsRendererCategory, QgsRuleBasedRenderer, QgsSymbol, QgsSymbolLayer,
    QgsTextFormat, QgsUnitTypes, QgsVectorLayer, QgsVectorLayerSimpleLabeling,
)
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
    return layer


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
    basemap = QgsRasterLayer(
        "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0",
        "basemap", "wms")
    basemap.hueSaturationFilter().setGrayscaleMode(QgsHueSaturationFilter.GrayscaleLightness)
    basemap.setOpacity(0.45)
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

    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = 150
    settings.appendGeoreference = False
    settings.exportMetadata = False
    result = QgsLayoutExporter(layout).exportToImage(str(IMAGE_FILE), settings)
    if result != QgsLayoutExporter.Success:
        sys.exit(f"map export failed with code {result}")


def strip_password(qgz_path, password):
    # strip password from saved project
    with zipfile.ZipFile(qgz_path) as z:
        files = {name: z.read(name) for name in z.namelist()}
    with zipfile.ZipFile(qgz_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            if name.endswith(".qgs"):
                data = re.sub(rb" password='[^']*'", b"", data)
            z.writestr(name, data)
    with zipfile.ZipFile(qgz_path) as z:
        if any(password.encode() in z.read(n) for n in z.namelist()):
            sys.exit("password is still in the project file, not saving it")


def main():
    app = QgsApplication([], False)
    app.initQgis()
    env = read_env()
    project = QgsProject.instance()

    extent = build_project(project, env)
    export_png(project, extent)
    print(f"saved {IMAGE_FILE}")

    project.write(str(PROJECT_FILE))
    strip_password(PROJECT_FILE, env["PGPASSWORD"])
    print(f"saved {PROJECT_FILE} without the database password")
    app.exitQgis()


if __name__ == "__main__":
    main()
