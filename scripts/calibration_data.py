"""
Generate the Calibration Dataset for the quantization process.

The Dataset is generated according to the algorithm described in Q-Diffusion at: https://arxiv.org/abs/2302.04304

"""
import argparse
import os

import torch as th
# import torch.distributed as dist
# import torchvision as tv

from guided_diffusion.image_datasets import load_data

# from guided_diffusion import dist_util, logger
from guided_diffusion.script_util import (
    model_and_diffusion_defaults,
    create_model_and_diffusion,
    add_dict_to_argparser,
    args_to_dict,
)

import numpy as np
import matplotlib.pyplot as plt
import os
from pooling import MedianPool2d

from pytorch_lightning import seed_everything

os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"

# SNR (var): 1 (0.9) 5 (0.6) 10 (0.36) 15 (0.22) 20 (0.13) 25 (0.08) 30 (0.05) 100 (0.0)
SNR_DICT = {100: 0.0,
            30: 0.05,
            25: 0.08,
            20: 0.13,
            15: 0.22,
            10: 0.36,
            5: 0.6,
            1: 0.9}

def preprocess_input(args, data, num_classes, one_hot_label=True):
    # move to GPU and change data types
    data['label'] = data['label'].long()

    # create one-hot label map
    label_map = data['label']
    if one_hot_label:
        bs, _, h, w = label_map.size()
        input_label = th.FloatTensor(bs, num_classes, h, w).zero_()

        # print("label_map.size()", label_map.size())

        input_semantics = input_label.scatter_(1, label_map, 1.0)

        # concatenate instance map if it exists
        if 'instance' in data:
            inst_map = data['instance']
            instance_edge_map = get_edges(inst_map)
            input_semantics = th.cat((input_semantics, instance_edge_map), dim=1)
    else:
        label_map = data['label']
        if 'instance' in data:
            # print("Instance in data")
            inst_map = data['instance']
            instance_edge_map = get_edges(inst_map)
            input_semantics = th.cat((label_map, instance_edge_map), dim=1)

    # print("Min, Mean, Max", th.min(input_semantics), th.mean(input_semantics), th.max(input_semantics))
    # input_semantics = (input_semantics - th.mean(input_semantics)) / th.std(input_semantics)
    # input_semantics = (input_semantics - th.min(input_semantics)) / (th.max(input_semantics - th.min(input_semantics)))
    # print("After norm: Min, Mean, Max", th.min(input_semantics), th.mean(input_semantics), th.max(input_semantics))

    # SNR (var): 1 (0.9) 5 (0.6) 10 (0.36) 15 (0.22) 20 (0.13) 25 (0.08) 30 (0.05) 100 (0.0)
    noise = th.randn(input_semantics.shape, device=input_semantics.device)*SNR_DICT[args.snr]
    input_semantics += noise
    print("Min, Mean, Max", th.min(input_semantics), th.mean(input_semantics), th.max(input_semantics))
    input_semantics = (input_semantics - th.min(input_semantics)) / (th.max(input_semantics) - th.min(input_semantics))
    print("Min, Mean, Max", th.min(input_semantics), th.mean(input_semantics), th.max(input_semantics))

    if args.pool == "med":
        print("Using Median filter")
        med_filter = MedianPool2d(padding=1, same=True)
        input_semantics_clean = med_filter(input_semantics)
    if args.pool == "mean":
        print("Using Average filter")
        avg_filter = th.nn.AvgPool2d(kernel_size=3, stride=1, padding=1)
        input_semantics_clean = avg_filter(input_semantics)
    else:
        input_semantics_clean = input_semantics

    # input_semantics_clean = ndimage.median_filter(input_semantics.numpy(), size=20, mode="nearest")
    # input_semantics_clean = np.array([])
    # for map in input_semantics:
    #     clean_map = np.array([])
    #     for channel in map:
    #         print(channel.shape)
    #         clean_channel = signal.medfilt2d(channel.numpy())
    #         clean_map = np.concatenate([clean_map, clean_channel], axis=0)
    #     input_semantics_clean = np.concatenate([input_semantics_clean, clean_map], axis=0)
    # input_semantics_clean = th.tensor(input_semantics_clean)
    # input_semantics = (input_semantics - th.mean(input_semantics)) / th.std(input_semantics)
    # print("After norm: Min, Mean, Max", th.min(input_semantics_clean), th.mean(input_semantics_clean), th.max(input_semantics_clean))
    # input_semantics = (input_semantics - th.min(input_semantics)) / (th.max(input_semantics - th.min(input_semantics)))

    plt.figure(figsize=(30,30))
    for idx, channel in enumerate(input_semantics_clean[0]):
        plt.subplot(6,6,idx+1)
        plt.imshow(channel.numpy(), cmap="gray")
        plt.axis("off")
    plt.savefig("./seg_map.png")

    return {'y': input_semantics_clean}

def preprocess_input_FDS(args, data, num_classes, one_hot_label=True):
    
    pool = "max"
    label_map = data['label'].long()

    # create one-hot label map
    # label_map = label.unsqueeze(0)
    bs, _, h, w = label_map.size()
    input_label = th.FloatTensor(bs, num_classes, h, w).zero_()
#     print("label map shape:", label_map.shape)

    input_semantics = input_label.scatter_(1, label_map, 1.0)
    print(input_semantics.shape)
    map_to_be_discarded = []
    map_to_be_preserved = []
    input_semantics = input_semantics.squeeze(0)
    for idx, segmap in enumerate(input_semantics.squeeze(0)):
        if 1 in segmap:
            map_to_be_preserved.append(idx)
        else:
            map_to_be_discarded.append(idx)

    # concatenate instance map if it exists
    if 'instance' in data:
        inst_map = data['instance']
        instance_edge_map = get_edges(inst_map)
        input_semantics = th.cat((input_semantics.unsqueeze(0), instance_edge_map), dim=1)
        #add instance map to map indexes
        map_to_be_preserved.append(num_classes)
        num_classes += 1

    print(input_semantics.shape, len(map_to_be_preserved))

    # input_semantics = input_semantics[map_to_be_preserved].unsqueeze(0)
    input_semantics = input_semantics[0][map_to_be_preserved]


    # if pool != None:
    #     avg_filter = th.nn.AvgPool2d(kernel_size=3, stride=1, padding=1)
    #     if 'instance' in data:
    #         instance_edge_map = avg_filter(instance_edge_map)
    #         input_semantics = th.cat((input_semantics.unsqueeze(0), instance_edge_map), dim=1)
    noise = th.randn(input_semantics.shape, device=input_semantics.device)*SNR_DICT[args.snr]

    input_semantics += noise

    if pool == "med":
        print("Using Median filter")
        med_filter = MedianPool2d(padding=1, same=True)
        input_semantics_clean = med_filter(input_semantics)
    elif pool == "mean":
        print("Using Average filter")
        avg_filter = th.nn.AvgPool2d(kernel_size=3, stride=1, padding=1)
        # avg_filter2 = th.nn.AvgPool2d(kernel_size=5, stride=1, padding=1)
        input_semantics_clean = avg_filter(input_semantics)
    elif pool == "max":
        print("Using Max filter")
        avg_filter = th.nn.AvgPool2d(kernel_size=3, stride=1, padding=1)
        max_filter = th.nn.MaxPool2d(kernel_size=3, stride=1, padding=1)
        input_semantics_clean = max_filter(avg_filter(input_semantics))

    else:
        input_semantics_clean = input_semantics

#     print("After norm: Min, Mean, Max", torch.min(input_semantics_clean), torch.mean(input_semantics_clean), torch.max(input_semantics_clean))
    # print("-->", input_semantics_clean.shape)
    input_semantics_clean = input_semantics_clean.unsqueeze(0)
    
    # Insert non-classes maps
#     print("input_semantics_clean", input_semantics_clean.shape)
    input_semantics = th.empty(size=(input_semantics_clean.shape[0],\
                                        num_classes, input_semantics_clean.shape[2],\
                                        input_semantics_clean.shape[3]), device=input_semantics_clean.device)
    # print("input_semantics", input_semantics.shape)
    # print("Preserved:", map_to_be_preserved, len(map_to_be_preserved))
    # print("Discarded:", map_to_be_discarded, len(map_to_be_discarded))
    # print("input_semantics_clean", input_semantics_clean[0].shape)
    input_semantics[0][map_to_be_preserved] = input_semantics_clean[0]
    input_semantics[0][map_to_be_discarded] = th.zeros((len(map_to_be_discarded), input_semantics_clean.shape[2], input_semantics_clean.shape[3]), device=input_semantics_clean.device)
    
    # plt.figure(figsize=(30,30))
    # for idx, channel in enumerate(input_semantics[0]):
    #     plt.subplot(6,6,idx+1)
    #     plt.imshow(channel.numpy(), cmap="gray")
    #     plt.axis("off")
    # plt.savefig("./seg_map.png")

    return {'y': input_semantics}

def get_edges(t):
    edge = th.ByteTensor(t.size()).zero_()
    edge[:, :, :, 1:] = edge[:, :, :, 1:] | (t[:, :, :, 1:] != t[:, :, :, :-1])
    edge[:, :, :, :-1] = edge[:, :, :, :-1] | (t[:, :, :, 1:] != t[:, :, :, :-1])
    edge[:, :, 1:, :] = edge[:, :, 1:, :] | (t[:, :, 1:, :] != t[:, :, :-1, :])
    edge[:, :, :-1, :] = edge[:, :, :-1, :] | (t[:, :, 1:, :] != t[:, :, :-1, :])
    return edge.float()

def create_argparser():
    defaults = dict(
        data_dir="",
        dataset_mode="",
        clip_denoised=True,
        num_samples=10000,
        batch_size=1,
        use_ddim=False,
        model_path="",
        results_path="",
        is_train=False,
        num_classes=35,
        s=1.0,
        snr=100,
        pool="med",
        add_noise=False,
        noise_to="semantics",
        # unet_model="unet" #"unet", "spadeboth", "enconly"
    )
    defaults.update(model_and_diffusion_defaults())
    parser = argparse.ArgumentParser()
    add_dict_to_argparser(parser, defaults)
    parser.add_argument("--seed", type=int, default=1234, help="Random seed")
    
    # Calibration specific Configs:
    # parser.add_argument(
    #     "--timesteps", type=int, default=1000, help="number of steps involved"
    # )
    parser.add_argument(
        "--cali_n", type=int, default=1024, 
        help="number of samples for each timestep for qdiff reconstruction"
    )
    parser.add_argument(
        "--cali_st", type=int, default=1, 
        help="number of timesteps used for calibration"
    )

    return parser

if __name__ == "__main__":
    # parse_args
    args = create_argparser().parse_args()

    # fix random seed
    seed_everything(args.seed)

    # Instanziate the Model
    print("Creating Model and Diffusion...")
    model, diffusion = create_model_and_diffusion(
        **args_to_dict(args, model_and_diffusion_defaults().keys())
    )
    # Load the state_dict from checkpoint
    checkpoint = th.load(args.model_path)
    new_state_dict = {key.replace('model.', ''): value for key, value in checkpoint.items()}
    model.load_state_dict(new_state_dict)
    # model.load_state_dict(th.load(args.model_path))
    if args.use_fp16:
        model.convert_to_fp16()
    model.to("cuda")
    model.eval()

    print("Creating Data Loader...")
    data_loader = load_data(
        dataset_mode=args.dataset_mode,
        data_dir=args.data_dir,
        batch_size=args.batch_size,
        image_size=args.image_size,
        class_cond=args.class_cond,
        deterministic=False,
        random_crop=False,
        random_flip=False,
        is_train=False
    )

    # Sampling Procedure:
    print("Start Sampling")
    device = "cuda:0"
    T = args.diffusion_steps    # Total Timesteps
    N = args.cali_n             # Number of Samples for each Timestep
    ds = int(T / args.cali_st)  # Sampling Interval
    assert()
    loop_fn = (
        diffusion.ddim_sample_loop_progressive
        if args.use_ddim
        else diffusion.p_sample_loop_progressive
    )
    xs_l = []
    ts_l = []
    cs_l = []
    for batch, (images, cond) in enumerate(data_loader):
        if (batch * args.batch_size >= args.cali_n):
            break
        print(f'batch {batch}:')
        # generate model_kwargs
        model_kwargs = preprocess_input_FDS(args, cond, num_classes=args.num_classes, one_hot_label=args.one_hot_label)
        model_kwargs['s'] = args.s
        for t, sample_t in enumerate(
            loop_fn(
                model,
                (args.batch_size, 3, args.image_size, args.image_size * 2),
                clip_denoised=args.clip_denoised,
                model_kwargs=model_kwargs,
                device=device,
                progress=True
            )
        ):
            if (t + 1) % ds == 0:
                print('t = {t}')
                xs_l.append(sample_t['sample'])
                ts_l.append((th.ones(args.batch_size) * t).float() * (1000.0 / T))
                cs_l.append(model_kwargs['y'])
    data = {
        'xs': th.cat(xs_l, 0),
        'ts': th.cat(ts_l, 0),
        'cs': th.cat(cs_l, 0)
    }
    print("Sampling Complete")
    print(f'xs: {data["xs"].shape}')
    print(f'ts: {data["ts"].shape}')
    print(f'cs: {data["cs"].shape}')
    th.save(data, 'cali_data.pth')