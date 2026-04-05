import os
import cv2
import threading
import time
import django
from django.utils import timezone
from django.db.models import Q
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from ultralytics import YOLO
from deepface import DeepFace

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YOLO_PATH = os.path.join(BASE_DIR, 'surveillance', 'models', 'yolo11n_models', 'yolo11n-pose.pt')
DEEPFACE_MODELS = os.path.join(BASE_DIR, 'surveillance', 'models')
SNAPSHOT_DIR = os.path.join(BASE_DIR, 'media', 'snapshots')

os.environ["DEEPFACE_HOME"] = DEEPFACE_MODELS
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def _save_detection_event(person_count, action, matched_target_id=None, matched_name='', frame=None):
    """
    Runs inside a plain thread — imports models here to avoid AppRegistry issues.
    Saves one DetectionEvent row. Skips 'Normal' events with zero people to avoid
    flooding the table; adjust the condition to your preference.
    """
    # Skip boring idle frames — only save if something is happening
    if person_count == 0 and action == 'Normal' and not matched_name:
        return

    try:
        from surveillance.models import DetectionEvent, TargetPerson

        snapshot_path = None
        if frame is not None:
            fname = f"snap_{int(time.time()*1000)}.jpg"
            full_path = os.path.join(SNAPSHOT_DIR, fname)
            cv2.imwrite(full_path, frame)
            snapshot_path = f"snapshots/{fname}"

        target_obj = None
        if matched_target_id:
            try:
                target_obj = TargetPerson.objects.get(pk=matched_target_id)
            except TargetPerson.DoesNotExist:
                pass

        DetectionEvent.objects.create(
            timestamp=timezone.now(),
            person_count=person_count,
            action=action,
            matched_target=target_obj,
            matched_target_name=matched_name,
            frame_snapshot=snapshot_path or '',
        )
    except Exception as e:
        # Never crash the engine thread because of a DB write failure
        print(f"[Engine] DetectionEvent save error: {e}")


class SurveillanceEngine(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running = False
        self.model = None
        self.channel_layer = get_channel_layer()
        self.targets = []
        # Pending DB writes queued from the engine loop, executed in a worker thread
        self._db_queue = []
        self._db_lock = threading.Lock()
        self._start_db_worker()

    # ------------------------------------------------------------------
    # DB worker — drains the queue in a separate thread so camera loop
    # is never blocked by a slow DB write.
    # ------------------------------------------------------------------
    def _start_db_worker(self):
        def worker():
            while True:
                task = None
                with self._db_lock:
                    if self._db_queue:
                        task = self._db_queue.pop(0)
                if task:
                    _save_detection_event(**task)
                else:
                    time.sleep(0.05)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _queue_save(self, **kwargs):
        with self._db_lock:
            self._db_queue.append(kwargs)

    # ------------------------------------------------------------------

    def load_resources(self):
        if self.model is None:
            self.model = YOLO(YOLO_PATH)

    def refresh_targets(self):
        """Fetch active (non-expired, not-found) targets from DB."""
        try:
            from surveillance.models import TargetPerson
            now = timezone.now()
            active = TargetPerson.objects.filter(is_found=False).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now)
            )
            self.targets = [
                {"id": t.pk, "name": t.name, "path": t.image.path}
                for t in active
            ]
        except Exception as e:
            print(f"[Engine] refresh_targets error: {e}")

    def run(self):
        self.running = True
        self.load_resources()
        cap = cv2.VideoCapture(0)
        frame_count = 0

        while self.running:
            success, frame = cap.read()
            if not success:
                time.sleep(1)
                continue

            # ---- 1. YOLO Pose Detection ----
            results = self.model.predict(source=frame, conf=0.5, verbose=False)
            person_count = len(results[0].boxes) if results else 0
            detected_action = 'Normal'

            if results and len(results[0].keypoints) > 0:
                for kpts in results[0].keypoints.data:
                    k = kpts.cpu().numpy()
                    try:
                        if k[0][1] > k[11][1]:
                            detected_action = 'FALL DETECTED'
                        elif k[9][1] < k[0][1]:
                            detected_action = 'HAND WAVING'
                    except Exception:
                        continue

            # ---- 2. Refresh targets every ~10 s (300 frames @ ~30 fps) ----
            if frame_count % 300 == 0:
                self.refresh_targets()

            # ---- 3. DeepFace check every 50 frames ----
            matched_id = None
            matched_name = ''
            if frame_count % 50 == 0 and person_count > 0 and self.targets:
                for target in self.targets:
                    try:
                        res = DeepFace.verify(
                            img1_path=frame,
                            img2_path=target['path'],
                            enforce_detection=False,
                            model_name='VGG-Face'
                        )
                        if res['verified']:
                            matched_id = target['id']
                            matched_name = target['name']
                            self.broadcast({
                                "type": "TARGET_MATCH",
                                "name": matched_name,
                                "target_id": matched_id,
                            })
                            # Save a snapshot on confirmed match
                            self._queue_save(
                                person_count=person_count,
                                action=detected_action,
                                matched_target_id=matched_id,
                                matched_name=matched_name,
                                frame=frame.copy(),
                            )
                    except Exception:
                        continue

            # ---- 4. Broadcast live stats ----
            self.broadcast({
                "type": "STAT_UPDATE",
                "count": person_count,
                "action": detected_action,
                "message": f"{person_count} Detected | {detected_action}",
            })

            # ---- 5. Queue DB write (non-blocking) ----
            # Only write when something noteworthy happens (not every idle frame)
            if detected_action != 'Normal' or matched_name:
                self._queue_save(
                    person_count=person_count,
                    action=detected_action,
                    matched_target_id=matched_id,
                    matched_name=matched_name,
                    frame=frame.copy() if detected_action == 'FALL DETECTED' else None,
                )

            frame_count += 1
            time.sleep(0.01)

        cap.release()

    def broadcast(self, data):
        """Send data to the dashboard surveillance group."""
        async_to_sync(self.channel_layer.group_send)(
            "surveillance_group",
            {"type": "forward_to_websocket", "payload": data},
        )

    def stop(self):
        self.running = False


# Global singleton
monitor = SurveillanceEngine()