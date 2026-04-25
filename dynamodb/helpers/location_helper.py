from aws_lambda_powertools import Logger
import boto3
import re
from typing import Any, List, Dict, Tuple
from constants.general import SERVICE_NAME
from constants.countries import COUNTRIES

# Module-level cache for parsed KML geometries — survives across warm invocations
_KML_GEOMETRY_CACHE: Dict[str, Tuple[List[str], Any]] = {}


class LocationHelper:
    """
    Shared helper for KML-based location badge resolution.
    Used by both StravaWorkoutHelper and AppleHealthWorkoutHelper.
    """

    def __init__(self, request_id: str = None):
        self.logger = Logger(service=SERVICE_NAME)
        if request_id:
            self.logger.append_keys(request_id=request_id)
        self._kml_cache: Dict[str, bytes] = {}

    def get_location_badges(
        self, workout_polyline: str, kml_file_name: str
    ) -> Dict[str, bool]:
        """
        Given an encoded polyline and a KML file name in S3, returns a dict
        mapping each location name to True/False based on route intersection.
        Uses an STRtree spatial index so only candidate polygons whose bounding
        boxes overlap the route are checked precisely.
        KML bytes are cached on the instance to avoid redundant S3 fetches within
        the same Lambda invocation.
        """
        import polyline as polyline_lib
        from lxml import etree
        from shapely.geometry import LineString, Polygon
        from shapely.ops import unary_union
        from shapely.strtree import STRtree

        try:
            if kml_file_name not in _KML_GEOMETRY_CACHE:
                self.logger.info(f"Building geometry index for {kml_file_name} (cold)")
                if kml_file_name not in self._kml_cache:
                    s3 = boto3.client("s3", region_name="us-west-2")
                    bucket = "workout-tracer-kml-files-851753231474-us-west-2-an"
                    self._kml_cache[kml_file_name] = s3.get_object(
                        Bucket=bucket, Key=kml_file_name
                    )["Body"].read()

                xml_tree = etree.fromstring(self._kml_cache[kml_file_name])
                ns = {"kml": "http://www.opengis.net/kml/2.2"}
                names = []
                geometries = []
                for placemark in xml_tree.findall(".//kml:Placemark", ns):
                    raw_name = placemark.findtext("kml:name", namespaces=ns)
                    name = re.sub(r"<[^>]+>", "", raw_name).strip()
                    if name in COUNTRIES:
                        name = COUNTRIES[name]
                    polys = []
                    for coord_el in placemark.findall(".//kml:coordinates", ns):
                        pts = [
                            (float(x), float(y))
                            for x, y, *_ in (
                                c.split(",") for c in coord_el.text.strip().split()
                            )
                        ]
                        if len(pts) >= 3:
                            polys.append(Polygon(pts))
                    if polys:
                        names.append(name)
                        geometries.append(unary_union(polys))

                _KML_GEOMETRY_CACHE[kml_file_name] = (names, STRtree(geometries))
                self.logger.info(
                    f"Geometry index built for {kml_file_name}: {len(names)} regions"
                )
            else:
                self.logger.info(
                    f"Using cached geometry index for {kml_file_name} (warm)"
                )

            names, spatial_index = _KML_GEOMETRY_CACHE[kml_file_name]
            coords = polyline_lib.decode(workout_polyline)
            line = LineString([(lon, lat) for lat, lon in coords])

            results = {name: False for name in names}
            for idx in spatial_index.query(line, predicate="intersects"):
                results[names[idx]] = True

            matched = [name for name, hit in results.items() if hit]
            self.logger.info(
                f"Location badges matched for kml_file={kml_file_name}: {matched}"
            )
            return results
        except Exception as e:
            self.logger.error(
                f"Error in get_location_badges for kml_file={kml_file_name}: {e}"
            )
            return {}
