# -*- coding: utf-8 -*-
import time
import RPi.GPIO as GPIO

from utils import detector_utils as detector_utils
import cv2
import tensorflow as tf
import datetime
import argparse

from src.spring import spring

detection_graph, sess = detector_utils.load_inference_graph()

# Load hand wash pattern
with open('./trajectory_x.csv') as f:
    reader = csv.reader(f)
    centers_x = [int(row[0]) for row in reader]

template1 = np.array(centers_x[270:300])
template1_vel = np.diff(template1)
template1_vel = savgol_filter(template1_vel, 11, 3)
template2 = np.array(centers_x[470:529])
template2_vel = np.diff(template2)
template2_vel = savgol_filter(template2_vel, 17, 3)
template3 = np.array(centers_x[470:529])
template3_vel = np.diff(template3)
template3_vel = savgol_filter(template3_vel, 11, 3)
template4 = np.array(centers_x[1126:1165])
template4_vel = np.diff(template4)
template4_vel = savgol_filter(template4_vel, 11, 3)

Y_ = [template1_vel, template2_vel, template3_vel, template4_vel]
E_ = [180, 1800, 2300, 3800]
pathes =[] 


# 超音波センサー(HC-SR04)制御クラス
class Sensor():
    def __init__(self):
        self.__TRIG = 19 # 物理番号19
        self.__ECHO = 21 # 物理番号21
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD) # 物理ピン番号で指定
        GPIO.setup(self.__TRIG,GPIO.OUT)
        GPIO.setup(self.__ECHO,GPIO.IN)

    def getDistance(self):
        GPIO.output(self.__TRIG, GPIO.LOW)
        # TRIG = HIGH
        GPIO.output(self.__TRIG, True)
        # 0.01ms後に TRIG = LOW
        time.sleep(0.00001)        
        GPIO.output(self.__TRIG, False)

        signaloff=0
        signalon=0
        # 発射時間
        while GPIO.input(self.__ECHO) == 0:
            signaloff = time.time()
        # 到着時間
        while GPIO.input(self.__ECHO) == 1:
            signalon = time.time()
        # 距離計算
        return (signalon - signaloff) * 17000

    def __del__(self):
        GPIO.cleanup()

def hand_detection(ini_time):
    cap = cv2.VideoCapture(args.video_source)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    fps = int(cap.get(cv2.CAP_PROP_FPS))
    im_width, im_height = (cap.get(3), cap.get(4))
    
    fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
    writer = cv2.VideoWriter(args.tmp_path, fourcc, fps, (im_width, im_height))


    # max number of hands we want to detect/track
    num_hands_detect = 1
    
    start_time = datetime.datetime.now()
    num_frames = 0
    count = 0

    centers_x = []
    centers_y = []
    detected_boxes = []

    cv2.namedWindow('Single-Threaded Detection', cv2.WINDOW_NORMAL)
    cv2.namedWindow('Hand wash status', cv2.WINDOW_NORMAL)

    while (time.time() - ini_time) <= 30:
        # Expand dimensions since the model expects images to have shape: [1, None, None, 3]
        ret, image_np = cap.read()
        # image_np = cv2.flip(image_np, 1)
        try:
            image_np = cv2.cvtColor(image_np, cv2.COLOR_BGR2RGB)
        except:
            print("Error converting to RGB")
            break

        # Actual detection. Variable boxes contains the bounding box cordinates for hands detected,
        # while scores contains the confidence for each of these boxes.
        # Hint: If len(boxes) > 1 , you may assume you have found atleast one hand (within your score threshold)

        boxes, scores = detector_utils.detect_objects(image_np,
                                                      detection_graph, sess)

        # draw bounding boxes on frame
        center_x, center_y, detected_box = detector_utils.draw_box_on_image(num_hands_detect, args.score_thresh,
                                                                            scores, boxes, im_width, im_height,
                                                                            image_np, args.display
                                                                            )
        if detected_box[0] is not None:
            count += 1

        centers_x.append(center_x)
        centers_y.append(center_y)
        detected_boxes.append(detected_box)

        # Calculate Frames per second (FPS)
        num_frames += 1
        elapsed_time = (datetime.datetime.now() - start_time).total_seconds()
        fps = num_frames / elapsed_time
        
        writer.write(cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR))

        if (args.display > 0):
            # Display FPS on frame
            if (args.fps > 0):
                detector_utils.draw_framecount_on_image(str(num_frames), image_np)
                detector_utils.draw_fps_on_image("FPS : " + str(int(fps)),
                                                 image_np)
            cv2.imshow('Single-Threaded Detection',
                       cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR))

            if cv2.waitKey(25) & 0xFF == ord('q'):
                break
        else:
            print("frames processed: ", num_frames, "elapsed time: ",
                  elapsed_time, "fps: ", str(int(fps)))

    cap.release()
    writer.release()
    cv2.destroyWindow('Single-Threaded Detection')

    return  centers_x, centers_y, detected_boxes

def action_recognition(query, boxes):
    cap = cv2.VideoCapture(args.tmp_path)

    fps = int(cap.get(cv2.CAP_PROP_FPS))
    im_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    im_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
    writer = cv2.VideoWriter(output_path, fourcc, fps, (im_width, im_height))

    start_time = datetime.datetime.now()
    num_frames = 0
    
    if visualize:
        cv2.namedWindow('Single-Threaded Detection', cv2.WINDOW_NORMAL)

    ## Action Recognition
    query = np.array(query)
    query_vel = np.diff(query)
    query_vel = savgol_filter(query_vel, 11, 3)

    X = query_vel
    for Y, E in zip(Y_, E_):
        for path, cost in spring(X, Y, E):
            pathes.extend(path[:,0])

    data = np.zeros(len(query))
    for i in range(len(query)):
        if i in pathes:
            data[i] = 1
        else:
            data[i] = 0

    # drawing AR result
    while cap.isOpened() and num_frames < len(data):
        # Expand dimensions since the model expects images to have shape: [1, None, None, 3]
        ret, image_np = cap.read()
        # image_np = cv2.flip(image_np, 1)
        try:
            image_np = cv2.cvtColor(image_np, cv2.COLOR_BGR2RGB)
        except:
            print("Error converting to RGB")
            break

        # Actual detection. Variable boxes contains the bounding box cordinates for hands detected,
        # while scores contains the confidence for each of these boxes.
        # Hint: If len(boxes) > 1 , you may assume you have found atleast one hand (within your score threshold)
        if ret == True:
            # draw bounding boxes on frame
            detected = detector_utils.draw_ARbbox_on_image(boxes[num_frames], im_width, im_height,
                                                                image_np, data[num_frames])

            # Calculate Frames per second (FPS)
            num_frames += 1
            elapsed_time = (datetime.datetime.now() - start_time).total_seconds()
            fps = num_frames / elapsed_time

            detector_utils.draw_framecount_on_image(str(num_frames), image_np)
            detector_utils.draw_fps_on_image("FPS : " + str(int(fps)), image_np)

            writer.write(cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR))
            if visualize:
                cv2.imshow('Single-Threaded Detection',
                           cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR))

            if cv2.waitKey(25) & 0xFF == ord('q'):
                break
            else:
                pass
                # print("frames processed: ", num_frames, "elapsed time: ",
                #       elapsed_time, "fps: ", str(int(fps)))
        else:
            break

    cap.release()
    writer.release()
    cv2.destroyAllWindows()

def main():
    sensor = Sensor()
    while True:
        distance = sensor.getDistance()
        print("{:.0f}cm".format(distance))

        if distance < 10:
            ini_time = time.time()
            print("Hand detection...")
            centers_x, centers_y, detected_boxes = hand_detection(ini_time)
            print("Action recognition...")
            action_recognition(query=centers_x, boxes=detected_boxes)
        time.sleep(0.1)
    del sensor

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-sth',
        '--scorethreshold',
        dest='score_thresh',
        type=float,
        default=0.3,
        help='Score threshold for displaying bounding boxes')
    parser.add_argument(
        '-fps',
        '--fps',
        dest='fps',
        type=int,
        default=0,
        help='Show FPS on detection/display visualization')
    parser.add_argument(
        '-src',
        '--source',
        dest='video_source',
        default=0,
        help='Device index of the camera.')
    parser.add_argument(
        '-tmp_path',
        '--tmp_path',
        dest='tmp_path',
        default='./tmp.mp4',
        help='Path to save tmp video.')
    parser.add_argument(
        '-output_path',
        '--output_path',
        dest='output_path',
        default='./output_AR.mp4',
        help='Path to save output video.')
    parser.add_argument(
        '-wd',
        '--width',
        dest='width',
        type=int,
        default=320,
        help='Width of the frames in the video stream.')
    parser.add_argument(
        '-ht',
        '--height',
        dest='height',
        type=int,
        default=180,
        help='Height of the frames in the video stream.')
    parser.add_argument(
        '-ds',
        '--display',
        dest='display',
        type=int,
        default=1,
        help='Display the detected images using OpenCV. This reduces FPS')
    parser.add_argument(
        '-num-w',
        '--num-workers',
        dest='num_workers',
        type=int,
        default=4,
        help='Number of workers.')
    parser.add_argument(
        '-q-size',
        '--queue-size',
        dest='queue_size',
        type=int,
        default=5,
        help='Size of the queue.')
    args = parser.parse_args()
    
    main()