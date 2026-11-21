"""Phone detection is probabilistic (COCO-SSD 'cell phone' class in the browser). Events are logged as
POTENTIAL detections with confidence for examiner review, never as proof of misconduct."""
import config
def evaluate(assessment, confidence):
    msg = "A possible mobile phone was detected in view. Logged for examiner review."
    term = "Possible phone detected (exam policy: terminate)" if assessment["phone_terminate"] and confidence >= config.PHONE_CONFIDENCE else None
    return msg, term
