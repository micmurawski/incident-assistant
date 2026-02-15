import asyncio
import hashlib
import os
from typing import Any, Coroutine, Optional
from urllib.parse import urlparse

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (CollectionInfo, Distance, FieldCondition,
                                  Filter, FilterSelector, MatchValue,
                                  VectorParams)

from agent.code_index.models import (IVectorStoreClient, PointStruct,
                                     VectorStoreSearchResult)
from agent.constants import CODEBASE_INDEX_DEFAULTS, QDRANT_DEFAULT_URL
from agent.telemetry_service import get_telemetry_service

logging = get_telemetry_service()


class VectorStoreClient(IVectorStoreClient):
    def __init__(
        self,
        workspace_path: str,
        vector_size: int,
        api_key: Optional[str] = None,
        url: Optional[str] = QDRANT_DEFAULT_URL,
    ):
        host, port, use_https = self.parse_url(url)
        self.client = AsyncQdrantClient(
            host=host, port=port, https=use_https, prefix=None, api_key=api_key, headers={"User-Agent": "micmur"}
        )

        hash = hashlib.sha256(workspace_path.encode()).hexdigest()
        self.workspace_path = workspace_path
        self.vector_size = vector_size
        self.default_collection_name = f"ws-{hash[:16]}"
        self.distance_metric = Distance.COSINE

    def parse_url(self, url: str) -> tuple[str, int, bool]:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        use_https = parsed.scheme == "https"
        return host, int(port), use_https == "https"

    async def get_collection_info(self, collection_name: str | None = None) -> Coroutine[Any, Any, CollectionInfo]:
        if collection_name is None:
            collection_name = self.default_collection_name
        try:
            collection_info = await self.client.get_collection(collection_name)
            return collection_info
        except Exception as e:
            logging.warning(
                f"[VectorStore] Warning during getCollectionInfo for {collection_name}. Collection may not exist or another error occurred: {e}"
            )
            return None

    async def initialize(self, collection_name: str | None = None) -> Coroutine[Any, Any, bool]:
        collection_name = collection_name or self.default_collection_name
        created = False
        try:
            collection_info: CollectionInfo | None = await self.get_collection_info(collection_name)
            if not collection_info:
                await self.client.create_collection(
                    collection_name,
                    vectors_config=VectorParams(size=self.vector_size, distance=self.distance_metric),
                    hnsw_config={"m": 64, "ef_construct": 512, "on_disk": True},
                )
                created = True
            else:
                vector_params: VectorParams = collection_info.config.params.vectors
                existing_vector_size = vector_params.size

                if existing_vector_size == self.vector_size:
                    created = False
                else:
                    created = await self._recreate_collection_with_new_dimension(existing_vector_size)

            await self._create_payload_indexes()
            return created
        except Exception as e:
            logging.warning(
                f"[VectorStore] Warning during initialize for {self.collection_name}. Collection may not exist or another error occurred: {e}"
            )
            raise e

    async def _recreate_collection_with_new_dimension(self, existing_vector_size: int, collection_name: str | None = None) -> Coroutine[Any, Any, bool]:
        collection_name = collection_name or self.default_collection_name
        logging.warning(
            f"[VectorStore] Collection {collection_name} exists with vector size {existing_vector_size}, but we need {self.vector_size}. Recreating collection..."
        )
        deletion_succeeded = False
        recreation_attempted = False
        try:
            logging.info(f"[VectorStore] Deleting existing collection {collection_name}...")
            await self.client.delete_collection(collection_name)
            deletion_succeeded = True
            logging.info(f"[VectorStore] Successfully deleted collection {collection_name}")
            await asyncio.sleep(100)
            verification_info = await self.get_collection_info(collection_name)

            if not verification_info:
                raise Exception("Collection deletion failed")

            logging.info(
                f"[VectorStore] Creating new collection {collection_name} with vector size {self.vector_size}..."
            )
            recreation_attempted = True
            await self.client.create_collection(
                collection_name,
                vectors_config={"size": self.vector_size, "distance": self.distance_metric},
                hnsw_config={"m": 64, "ef_construction": 512, "on_disk": True},
            )
            logging.info(f"[VectorStore] Successfully created new collection {collection_name}")
            return True
        except Exception as e:
            context: str
            if not deletion_succeeded:
                context = f"Failed to delete existing collection with vector size {existing_vector_size}. {e}"
            elif not recreation_attempted:
                context = (
                    f"Deleted existing collection, but failed to recreate with vector size {self.vector_size}. {e}"
                )
            else:
                context = f"Failed to delete and recreate collection with vector size {self.vector_size}. {e}"

            logging.error(
                f"[VectorStore] Failed to recreate collection {collection_name} for dimension change ({existing_vector_size} -> ${self.vector_size}). {context}"
            )
            raise e

    async def _create_payload_indexes(self, collection_name: str | None = None) -> Coroutine[Any, Any, None]:
        collection_name = collection_name or self.default_collection_name
        for i in range(0, 5):
            try:
                await self.client.create_payload_index(
                    collection_name, field_name=f"path_segments.{i}", field_schema="keyword"
                )
            except Exception as e:
                logging.warning(
                    f"[VectorStore] Warning during createPayloadIndex for {collection_name}. Field {f'path_segments.{i}'} may already exist or another error occurred: {e}"
                )

    async def delete_points_by_file_path(self, file_path: str) -> Coroutine[Any, Any, None]:
        return await self.delete_points_by_multiple_file_paths([file_path])

    async def delete_points_by_multiple_file_paths(self, file_paths: list[str], collection_name: str | None = None) -> Coroutine[Any, Any, None]:
        collection_name = collection_name or self.default_collection_name
        if not file_paths:
            return
        try:
            collection_info = await self.get_collection_info(collection_name)
            if not collection_info:
                logging.warning(f"[VectorStore] Collection {collection_name} does not exist")
                return
            workspace_root = self.workspace_path
            filters = []
            for file_path in file_paths:
                if os.path.isabs(file_path):
                    rel_path = os.path.relpath(file_path, workspace_root)
                else:
                    rel_path = file_path
                normalized_rel_path = os.path.normpath(rel_path)
                segments = [seg for seg in normalized_rel_path.split(os.sep) if seg]

                must_conditions = [
                    FieldCondition(key=f"path_segments.{idx}", match=MatchValue(value=segment))
                    for idx, segment in enumerate(segments)
                ]
                filters.append(Filter(must=must_conditions))

            if len(filters) == 1:
                filter_obj = filters[0]
            else:
                filter_obj = Filter(should=filters)
            # Check if filters would match any points before attempting delete
            # count_result = await self.client.count(self.collection_name, count_filter=filter_obj, exact=True)#####
            # print(count_result.json())
            await self.client.delete(collection_name, FilterSelector(filter=filter_obj), wait=True)
        except Exception as e:
            logging.error(
                f"[VectorStore] Failed to delete points by multiple file paths {len(file_paths)} files in {self.collection_name}, sample file paths: {file_paths[:5]}. {e}"
            )
            raise e

    async def upsert_points(self, points: list[PointStruct], collection_name: str | None = None) -> Coroutine[Any, Any, None]:
        collection_name = collection_name or self.default_collection_name
        try:
            processed_points = []
            for point in points:
                payload = point.payload
                file_path = payload.file_path
                if file_path:
                    segments = [seg for seg in file_path.split(os.sep) if seg]
                    path_segments = {str(i): segment for i, segment in enumerate(segments)}
                    new_payload = payload.to_dict()
                    new_payload["path_segments"] = path_segments
                    new_point = point.to_dict()
                    new_point["payload"] = new_payload
                    processed_points.append(new_point)
                else:
                    processed_points.append(point)
            await self.client.upsert(collection_name, points=processed_points, wait=True)
        except Exception as e:
            logging.error(f"[VectorStore] Failed to upsert points for {collection_name}. {e}")
            raise e

    def _is_payload_valid(self, payload: Any) -> bool:
        if not payload:
            return False
        valid_keys = ["file_path", "code_chunk", "start_line", "end_line", "key"]
        has_all_keys = all(key in payload for key in valid_keys)
        return has_all_keys

    async def search(
        self,
        query_vector: list[float],
        directory_prefix: Optional[str] = None,
        min_score: Optional[float] = None,
        max_results: Optional[int] = None,
        collection_name: str | None = None,
    ) -> list[VectorStoreSearchResult]:
        collection_name = collection_name or self.default_collection_name
        try:
            filter = None
            if directory_prefix:
                normalized_prefix = os.path.normpath(directory_prefix.replace("\\", "/"))
                if normalized_prefix == "." or normalized_prefix == "./":
                    filter = None
                else:
                    if normalized_prefix.startswith("./"):
                        cleaned_prefix = os.path.normpath(normalized_prefix[2:])
                    else:
                        cleaned_prefix = os.path.normpath(normalized_prefix)
                    segments = [seg for seg in cleaned_prefix.split("/") if seg]

                    if segments:
                        filter = {
                            "must": [
                                {"key": f"path_segments.{idx}", "match": {"value": segment}}
                                for idx, segment in enumerate(segments)
                            ]
                        }
            search_req = {
                "query_vector": query_vector,
                "filter": filter,
                "score_threshold": min_score if min_score else CODEBASE_INDEX_DEFAULTS["DEFAULT_SEARCH_MIN_SCORE"],
                "limit": max_results if max_results else CODEBASE_INDEX_DEFAULTS["DEFAULT_SEARCH_RESULTS"],
                "params": {"hnsw_ef": 128, "exact": False},
                "with_payload": {"include": ["file_path", "code_chunk", "start_line", "end_line", "path_segments"]},
            }
            res = await self.client.search(collection_name, search_req)
            filtered_points = filter(lambda point: self._is_payload_valid(point.payload), res)
            return [
                VectorStoreSearchResult(id=point.id, score=point.score, payload=point.payload)
                for point in filtered_points
            ]
        except Exception as e:
            logging.error(f"[VectorStore] Failed to search for points. {e}")
            raise e

    async def clear_collection(self, collection_name: str | None = None) -> Coroutine[Any, Any, None]:
        collection_name = collection_name or self.default_collection_name
        try:
            await self.client.delete_collection(collection_name)
        except Exception as e:
            logging.error(f"[VectorStore] Failed to clear collection {collection_name}. {e}")
            raise e

    async def delete_collection(self, collection_name: str | None = None) -> Coroutine[Any, Any, None]:
        collection_name = collection_name or self.default_collection_name
        try:
            collection_info = await self.get_collection_info(collection_name)
            if collection_info:
                await self.client.delete_collection(collection_name)
        except Exception as e:
            logging.error(f"[VectorStore] Failed to delete collection {collection_name}. {e}")
            raise e
