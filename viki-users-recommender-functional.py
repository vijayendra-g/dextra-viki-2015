from __future__ import division
from sklearn.preprocessing import StandardScaler

import pandas as pd
import time
import csv
import numpy as np
import os
import datetime
import re

## ==================== Data preparation
print "=> Reading data"
print datetime.datetime.now()
videos_matrix = pd.read_csv('./Data/videos_similarity_matrix.csv',sep='\t')
videos_matrix = videos_matrix.drop('sim_country', 1)
videos_matrix = videos_matrix.drop('sim_language', 1)
videos_matrix = videos_matrix.drop('sim_adult', 1)
videos_matrix = videos_matrix.drop('sim_content_owner_id', 1)
videos_matrix = videos_matrix.drop('sim_broadcast', 1)
videos_matrix = videos_matrix.drop('sim_season', 1)
videos_matrix = videos_matrix.drop('sim_episode_count', 1)
videos_matrix = videos_matrix.drop('sim_genres', 1)
videos_matrix = videos_matrix.drop('sim_cast', 1)
videos_matrix = videos_matrix.drop('jaccard', 1)
# remove self-similarity entries
videos_matrix = videos_matrix[videos_matrix['video_id_left'] != videos_matrix['video_id_right']]
# Top 5 similar videos to each video
videos_matrix = videos_matrix.sort(['sim_combined'], ascending=False).groupby('video_id_left').head(5)

behaviors = pd.read_csv('./Data/20150701094451-Behavior_training.csv') # for each user, work out the
behaviors = behaviors.drop('date_hour', 1)
behaviors = behaviors.drop('mv_ratio', 1)

# Top 10, should be enough # remember to exclude from watched_videos later on
hot_videos = behaviors.groupby('video_id').agg(['count']).sort([('score', 'count')], ascending=False).head(10).index.tolist()

print "=> Processing matrixes"
print datetime.datetime.now()

user_history_videos_matrix = pd.merge(behaviors, videos_matrix, left_on=['video_id'], right_on=['video_id_left'])

# weighted_sim_combined
def weighted_sim_combined(row):
    return row['score'] * row['sim_combined']

user_history_videos_matrix['weighted_sim_combined'] = user_history_videos_matrix.apply(weighted_sim_combined, axis=1)
user_history_videos_matrix = user_history_videos_matrix.drop('score', 1)
user_history_videos_matrix = user_history_videos_matrix.drop('video_id_left', 1)
user_history_videos_matrix = user_history_videos_matrix.drop('sim_combined', 1)

# TODO: Remove similar from the top3 list. Make sure not recommending the same
# Not too urgently - it's very rare that this happen, because someone has to have less than 3 recommendations.

# group on user_level - video_id
grouped_user_history_videos_matrix = user_history_videos_matrix.groupby(['user_id', 'video_id_right'],as_index=False).aggregate(np.sum)

# For filtering purpose (do not recommend watched videos)
behaviors = behaviors.drop('score', 1)
grouped_behaviors = pd.DataFrame({ 'video_ids' : behaviors.groupby('user_id').apply(lambda x: list(x.video_id))}) # user_id, list_of_video_ids
grouped_behaviors['user_id'] = grouped_behaviors.index
grouped_user_history_videos_matrix = pd.merge(grouped_user_history_videos_matrix, grouped_behaviors, on=['user_id'])

grouped_user_history_videos_matrix = grouped_user_history_videos_matrix[grouped_user_history_videos_matrix.apply(lambda x: x['video_id_right'] not in x['video_ids'], axis=1)]
grouped_user_history_videos_matrix = grouped_user_history_videos_matrix.drop('video_ids', 1) # user_id, video_id_right, weighted_sim_combined

# user - top3 videos
grouped_user_history_videos_matrix = grouped_user_history_videos_matrix.sort(['weighted_sim_combined'], ascending=False).groupby('user_id').head(3)
grouped_user_history_videos_matrix = pd.DataFrame({ 'recommendations' : grouped_user_history_videos_matrix.groupby('user_id').apply(lambda x: list(x.video_id_right))})
grouped_user_history_videos_matrix['user_id'] = grouped_user_history_videos_matrix.index


print "=> Processing results"
print datetime.datetime.now()
# separated by '-1,DEXTRA' and '-2,DEXTRA' (removed)
test1 = pd.read_csv('./Data/20150701094451-Sample_submission-p1.csv')
test2 = pd.read_csv('./Data/20150701094451-Sample_submission-p2.csv')
submit1 = pd.merge(test1, grouped_user_history_videos_matrix, on=['user_id'], how='left')
submit1['count'] = submit1.index
submit2 = pd.merge(test2, grouped_user_history_videos_matrix, on=['user_id'], how='left')
submit2['count'] = submit2.index
def recommendation(row):
  try:
    return row['recommendations'][row['count'] % 3]
  except:
    return hot_videos[row['count'] % 3]

submit1['video_id'] = submit1.apply(recommendation, axis=1)
submit2['video_id'] = submit2.apply(recommendation, axis=1)
submit1 = submit1.drop('recommendations', 1)
submit1 = submit1.drop('count', 1)
submit2 = submit2.drop('recommendations', 1)
submit2 = submit2.drop('count', 1)

print "=> Writing result to CSV"
print datetime.datetime.now()
with open('./data/my_submit.csv', 'w') as f:
    writer = csv.writer(f, lineterminator='\n')
    writer.writerow(submit1.columns)
    writer.writerows(submit1.values)
    writer.writerow(['-1','DEXTRA'])
    writer.writerows(submit2.values)
    writer.writerow(['-2','DEXTRA'])