"""Policy for camera/navigation events. Detection runs in the browser (TensorFlow.js COCO-SSD), so no video
leaves the student's device; only event metadata (type, confidence, timestamp) is sent to the server."""
import config
NAV = {"tab_hidden", "fullscreen_exit", "window_blur"}

def evaluate(typ, session, assessment):
    """Return (message, terminate_reason, column_to_update, new_count)."""
    if typ in NAV and assessment["nav_monitoring"]:
        n = session["nav_warnings"] + 1; lim = assessment["warning_limit"]
        if n > lim: return None, "Navigation rule violated more than the allowed limit", "nav_warnings", n
        return f"Navigation warning {n} of {lim}: please stay on the exam window.", None, "nav_warnings", n
    if typ == "face_absence":
        n = session["face_warnings"] + 1
        if n > config.FACE_ABSENCE_LIMIT: return None, "Repeated sustained face absence", "face_warnings", n
        m = "Warning 1: Please remain within your camera view." if n == 1 else "Final warning: Please remain in front of your camera."
        return m, None, "face_warnings", n
    if typ == "multiple_faces": return "More than one person was detected. Flagged for examiner review.", None, None, 0
    if typ == "camera_lost": return "Camera disconnected. Please reconnect your camera.", None, None, 0
    return None, None, None, 0
