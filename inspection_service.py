from inference_service import predict


def inspect(image_path):
    """
    Run AI model on an inspection image.
    """
    return predict(image_path)