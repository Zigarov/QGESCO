## QGESCO:

### Quantize GESCO
* Train your own model or download our pretrained weights of GESCO [here](https://drive.google.com/file/d/1lW8J4gcZ3SS9r-kpEBMrVUfbC6mNLUP4/view?usp=drive_link).
* Download the Calibration Dataset (Cityscapes) [here](https://drive.google.com/file/d/1Su6rQ_ExUnNAj7srACu8v-lqdccATB-4/view?usp=sharing)
* save both files in the project directory
* Install the file `requirements.txt`
* Run the following command:

```
python scripts/quantize_model.py --data_dir ./data_val --dataset_mode cityscapes --attention_resolutions 32,16,8 --diffusion_steps 100 --use_ddim True --image_size 256 --learn_sigma True --noise_schedule linear --num_channels 256 --num_head_channels 64 --num_res_blocks 2 --resblock_updown True --use_fp16 False --use_scale_shift_norm True --num_classes 35 --class_cond True --no_instance False --batch_size 1 --model_path ./Cityscapes_ema_0.9999_190000.pt --results_path ./logs --s 2 --one_hot_label True --snr 100 --pool None --unet_model unet --use_pretrained --timesteps 100 --eta 0 --skip_type quad --ptq --weight_bit 8 --quant_mode qdiff --split --logdir ./logs --cond --cali_n 51 --cali_st 5 --cali_iters 20000 --cali_batch_size 1 --cali_data_path ./cali_data_256.pth
```

The quantized model will be saved in the corresponding log directory as `quantized_model.pth`