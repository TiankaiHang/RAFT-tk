import sys
sys.path.append('core')

import argparse
import os
import cv2
import glob
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from raft import RAFT
from utils import flow_viz
from utils.utils import InputPadder

from torchvision.io import read_video


DEVICE = 'cuda'

def load_image(imfile):
    img = np.array(Image.open(imfile)).astype(np.uint8)
    img = torch.from_numpy(img).permute(2, 0, 1).float()
    return img[None].to(DEVICE)


def viz(img, flo, fn):
    img = img[0].permute(1,2,0).cpu().numpy()
    flo = flo[0].permute(1,2,0).cpu().numpy()
    
    # map flow to rgb image
    flo = flow_viz.flow_to_image(flo)
    img_flo = np.concatenate([img, flo], axis=0)

    # import matplotlib.pyplot as plt
    # plt.imshow(img_flo / 255.0)
    # plt.show()

    # cv2.imshow('image', img_flo[:, :, [2,1,0]]/255.0)
    # cv2.waitKey()
    cv2.imwrite(fn, img_flo[:, :, [2,1,0]])


def demo(args):
    model = torch.nn.DataParallel(RAFT(args))
    model.load_state_dict(torch.load(args.model))

    model = model.module
    model.to(DEVICE)
    model.eval()

    with torch.no_grad():
        images = glob.glob(os.path.join(args.path, '*.png')) + \
                 glob.glob(os.path.join(args.path, '*.jpg'))

        os.makedirs(f"{args.path}/flow", exist_ok=True)
        
        images = sorted(images)
        idx = 0
        for imfile1, imfile2 in zip(images[:-1], images[1:]):
            image1 = load_image(imfile1)
            image2 = load_image(imfile2)

            padder = InputPadder(image1.shape)
            image1, image2 = padder.pad(image1, image2)

            flow_low, flow_up = model(image1, image2, iters=20, test_mode=True)
            viz(image1, flow_up, fn=f"{args.path}/flow/{idx}.png")
            idx += 1


def demo_video(args):
    model = torch.nn.DataParallel(RAFT(args))
    model.load_state_dict(torch.load(args.model))

    model = model.module
    model.to(DEVICE)
    model.eval()

    with torch.no_grad():
        
        videos_to_predict = os.listdir("data")
        videos_to_predict = [_v for _v in videos_to_predict if _v.endswith(".mp4")]

        for vid in videos_to_predict:
            # T H W C
            video_tensor = read_video(os.path.join("data", vid), pts_unit='sec')[0]
            video_tensor = video_tensor.permute(0, 3, 1, 2).float().to(DEVICE)
            # video_tensor = F.interpolate(video_tensor, size=(512, 512), mode="bicubic")
            print(video_tensor.dtype)
            os.makedirs(f"data/flow/{vid.split('.')[0]}", exist_ok=True)

            idx = 0
            T = video_tensor.shape[0]
            for i in range(T - 1):
                image1 = video_tensor[i][None]
                image2 = video_tensor[i + 1][None]

                padder = InputPadder(image1.shape)
                image1, image2 = padder.pad(image1, image2)

                flow_low, flow_up = model(image1, image2, iters=20, test_mode=True)
                viz(image2, flow_up, fn=f"data/flow/{vid.split('.')[0]}/{idx}.png")
                idx += 1
        

def concat_frames():
    videos_to_predict = os.listdir("data")
    videos_to_predict = [_v for _v in videos_to_predict if _v.endswith(".mp4")]

    overall = []

    for vid in videos_to_predict:
        print(vid)
        current_video_flow = []
        flow_dir = f"data/flow/{vid.split('.')[0]}"
        flows = os.listdir(flow_dir)
        for i in range(len(flows)):
            current_video_flow.append(
                cv2.imread(os.path.join(flow_dir, f"{i}.png"))
            )

        overall.append(
            np.concatenate(current_video_flow, axis=1)
        )

    overall = np.concatenate(overall, axis=0)
    cv2.imwrite("data/flow-compare.png", overall)
        


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', help="restore checkpoint")
    parser.add_argument('--path', help="dataset for evaluation")
    parser.add_argument('--small', action='store_true', help='use small model')
    parser.add_argument('--mixed_precision', action='store_true', help='use mixed precision')
    parser.add_argument('--alternate_corr', action='store_true', help='use efficent correlation implementation')
    args = parser.parse_args()

    # demo(args)
    demo_video(args)
    concat_frames()
