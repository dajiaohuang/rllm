import pandas as pd
from functools import partial
import sys

sys.path.append("../src")
from utils.helper import data2text,write_jsonl
import models.lora_gptj as GPTJ
from run_exps_helper import *
import torch
from sklearn.preprocessing import MultiLabelBinarizer

sys.path.append("../../../")
from rllm.utils import macro_f1_score, micro_f1_score, get_llm_chat_cost

time_start = time.time()

def data2text(row, label = True, init = '', end = ''):
    prompt = init 
    prompt += ' Title:'+str(row['Title']).replace("'", "").replace('"', '')\
        # +' Year:'+ str(row['Year']).replace("'", "").replace('"', '')\
        # +' Director:'+str(row['Director']).replace("'", "").replace('"', '')\
        # +' Cast:'+str(row['Cast'])+' Runtime:'+str(row['Runtime']).replace("'", "").replace('"', '')\
        # +' Languages:'+ str(row['Languages']).replace("'", "").replace('"', '')\
        # +' Certificate:'+str(row['Certificate']).replace("'", "").replace('"', '')\
        # +' Plot:'+str(row['Plot']).replace("'", "").replace('"', '')
    prompt += end

    if not label:
        final_prompt = f"{prompt}###"
    else:
        completion = row['Genre']
        final_prompt = "{\"prompt\":\"%s###\", \"completion\":\"%s@@@\"}" % (prompt, completion)
    return final_prompt

def df2propmts(df, data2text_func, init = '', end = ''):
    jsonl = df.apply(func = partial(data2text_func, init = init, end = end), axis = 1).tolist()
    return jsonl

parser = argparse.ArgumentParser(description='')
parser.add_argument("-g", "--gpu_id", default=0, type=int)
parser.add_argument("--local_rank", default=-1, type=int)
parser.add_argument("--seed", default=12345, type=int)
parser.add_argument("-p", "--is_permuted", action="store_true")

parser.add_argument("-v", "--eval", default=0, type=int)
args = parser.parse_args()

device = torch.device(f'cuda:{args.gpu_id}') if torch.cuda.is_available() else 'cpu'
torch.cuda.set_device(args.gpu_id)

users = pd.read_csv(
    '../../../rllm/datasets/rel-movielens1m/classification/users.csv')
train = pd.read_csv(
    '../../../rllm/datasets/rel-movielens1m/classification/movies/train.csv')
val = pd.read_csv(
    '../../../rllm/datasets/rel-movielens1m/classification/movies/validation.csv')
test = pd.read_csv(
    '../../../rllm/datasets/rel-movielens1m/classification/movies/test.csv')
ratings = pd.read_csv(
    '../../../rllm/datasets/rel-movielens1m/classification/ratings.csv')

init='Given information about a movie: '
end = 'What is the genres it may belong to? Note: 1. Give the answer as following format: genre_1|genre_2|...|genre_n 2. The answer must only be chosen from followings:Documentary, Adventure, Comedy, Horror, War, Sci-Fi, Drama, Mystery, Western, Action, Children, Musical, Thriller, Crime, Film-Noir, Romance, Animation, Fantasy 3. Do not saying anything else. A: '

train_prompts = df2propmts(train, data2text, init, end)
val_prompts = df2propmts(val, data2text, init, end)
test_prompts = df2propmts(test, data2text, init, end)


write_jsonl('\n'.join(train_prompts),'train.json')
write_jsonl('\n'.join(val_prompts),'val.json')
write_jsonl('\n'.join(test_prompts),'test.json')

y_val = val['Genre']
y_test = test['Genre']





# gpt = GPTJ.LoRaQGPTJ(adapter=True, device=device,model_name='hivemind/gpt-j-6B-8bit')
gpt = GPTJ.LoRaQGPTJ(adapter=True, device=device)
train_configs={'learning_rate': 1e-5, 'batch_size': 1, 'epochs':1,  'weight_decay': 0.01, 'warmup_steps': 6}
gpt.finetune('data/train.json', 'data/val.json', train_configs, saving_checkpoint=False)

y_pred= query(gpt, test_prompts,bs=4)

print(y_pred)

# acc = get_accuracy(y_pred, y_test)
# print(acc)

movie_genres = test["Genre"].str.split("|")
all_genres = list(set([genre for genres in movie_genres for genre in genres]))

mlb = MultiLabelBinarizer(classes=all_genres)
real_genres_matrix = mlb.fit_transform(movie_genres)
pred_genres_matrix = mlb.fit_transform(y_pred)
macro_f1 = macro_f1_score(real_genres_matrix, pred_genres_matrix)
micro_f1 = micro_f1_score(real_genres_matrix, pred_genres_matrix)

time_end = time.time()

print(f"macro_f1: {macro_f1}")
print(f"micro_f1: {micro_f1}")
print(f"Total time: {time_end - time_start}s")
# print(f"Total USD$: {total_cost}")