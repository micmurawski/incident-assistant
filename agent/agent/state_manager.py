from typing import Any, Coroutine, Literal

TypeStatus = Literal["stand_by", "indexing", "indexed ", "error"]


class CodeIndexStateManager:
    _status: TypeStatus = "stand_by"
    _status_message: str | None = None
    _processed_items: int = 0
    _total_items: int = 0
    _current_item_unit: Literal["blocks", "files"] = "blocks"
    _progress_emitter = None

    def status(self) -> dict[str, Any]:
        return {
            "status": self._status,
            "status_message": self._status_message,
            "processed_items": self._processed_items,
            "total_items": self._total_items,
            "current_item_unit": self._current_item_unit,
        }

    def set_status(self, status: TypeStatus, status_message: str | None = None) -> Coroutine[Any, Any, None]:
        state_changed = status != self._status
        if state_changed:
            self._status = status
            if status_message:
                self._status_message = status_message
            if status == "indexing":
                self._processed_items = 0
                self._total_items = 0
                self._current_item_unit = "blocks"
                if status == "stand_by" and status_message is None:
                    self._status_message = "Ready"
                if status == "indexed" and status_message is None:
                    self._status_message = "Index up-to-date"
                if status == "error" and status_message is None:
                    self._status_message = "Error occurred"

    def report_file_queue_progress(self, processed_files: int, total_files: int, current_file_basename: str):
        process_changed = processed_files != self._processed_items or total_files != self._total_items
        if process_changed or self._status != "indexing":
            self._processed_items = processed_files
            self._total_items = total_files
            self._current_item_unit = "files"
            self._status = "indexing"

            # message: str
            # if total_files > 0 and processed_files < total_files:
            #    message = f"Processing {processed_files} / {total_files} {self._current_item_unit}, Current: {current_file_basename or "..."}"
            # elif total_files > 0 and processed_files == total_files:
            #    message = f"Finished processing {total_files} {self._current_item_unit} from queue."
            # else:
            #    message = "File queue processed"

            # old_status = self._status
            # old_message = self._status_message
            # self._status_message = message

            # if old_status != self._system_status or old_message != self._status_message or self._status != "indexing":
            #    # fire emmiter
