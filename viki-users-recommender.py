from __future__ import division
from sklearn.preprocessing import StandardScaler

import pandas as pd
import time
import csv
import numpy as np
import os
import datetime
import math

sim_features = ['sim_country', 'sim_language', 'sim_adult',
                'sim_content_owner_id', 'sim_broadcast', 'sim_episode_count',
                'sim_genres', 'sim_cast', 'hotness',
                'jaccard_1_3', 'jaccard_2_3', 'jaccard_3_3']

weight_features = [0,0,0,
                   0,0,0,
                   0,0,0,
                   1,3,5]

weight_scores = [1,2,3]
""" weight_scores:
How important a video user watched affects his recommended videos
In order words, if A watch V1 for 5% (score = 1) of its duration, and V2 for 95% (score = 3) of its duration,
V2 will be `weight_score[2] / weight_score[0]` times more important than V1 in respect to A's recommendations
"""

def read_data():
    """ Read and pre-process data
        >>> (behaviors, videos, videos_matrix) = read_data()
        >>> behaviors[:2]
            user_id   video_id   score
        0    759744      TV003       1
        1    759744      TV015       2
        >>> videos[:2]
          video_id broadcast_from
        0    TV001           None
        1    TV002        2013-06
        >>> videos_matrix[:2]
               video_id_left video_id_right  sim_combined
        287379         TV462          TV177   1947.746013
        287206         TV462          TV004   1947.746013
    """
    behaviors = pd.read_csv('./data/20150701094451-Behavior_training.csv')
    videos = pd.read_csv('./data/20150701094451-Video_attributes.csv')
    videos_matrix = pd.read_csv('./data/videos_similarity_matrix.csv')
    # Remove unused columns
    behaviors = behaviors.drop(['date_hour','mv_ratio'], 1)
    videos = videos.drop(['container_id','origin_country','origin_language','adult',
                          'broadcast_to','season_number','content_owner_id','genres',
                          'episode_count'], 1)
    # Pre-process videos_matrix
    videos_matrix = videos_matrix[videos_matrix['video_id_left'] != videos_matrix['video_id_right']]
    # Feature scaling:
    scaler = StandardScaler()
    for col in sim_features:
        scaler.fit(list(videos_matrix[col]))
        videos_matrix[col] = scaler.transform(videos_matrix[col])
    # Combined
    def sim_combined(row):
        score = 0
        for i in range(0, len(sim_features)):
            if row[sim_features[i]] > 0:
                score += row[sim_features[i]]*weight_features[i]
            # with standard scaler, feature similarity can be below zero.
            # do not punish them in this case, esp. with jaccard scores.
        return score
    videos_matrix['sim_combined'] = videos_matrix.apply(sim_combined, axis=1)
    # Top 5 similar videos to each video - 5 should be enough since we are only recommending 3 videos per person
    videos_matrix = videos_matrix.sort(['sim_combined'], ascending=False).groupby('video_id_left').head(5)
    videos_matrix = videos_matrix.drop(['sim_country', 'sim_language', 'sim_adult', 'sim_content_owner_id',
                                        'sim_broadcast', 'sim_season', 'sim_episode_count', 'sim_genres',
                                        'sim_cast', 'hotness', 'jaccard_1_3', 'jaccard_2_3', 'jaccard_3_3'],1)
    return (behaviors, videos, videos_matrix)

def unwatched_hot_videos(behaviors, videos):
    """ To compute a list of hot videos specific to each user, removing those that he/she already watched
        >>> users_hot_videos = unwatched_hot_videos(behaviors, videos)
        >>> users_hot_videos[:2]
            user_id  hot_videos_unwatched
        0   1        [TV001, TV419, TV412, TV413, TV414, TV415, TV4...
        1   3        [TV001, TV419, TV412, TV413, TV414, TV415, TV4...
    """
    videos_views = behaviors.groupby('video_id').agg(['count']).sort([('score', 'count')], ascending=False)
    def hotness(row):
        try:
            bf_date = datetime.datetime.strptime(row['broadcast_from'], "%Y-%m").date()
            day_2015_02 = datetime.datetime.strptime('2015-02', "%Y-%m").date()
            user_watched = videos_views[videos_views.index==row['video_id']].reset_index().score['count'][0]
            return  user_watched / (day_2015_02-bf_date).days
        except:
            return 0
    videos['hotness'] = videos.apply(hotness, axis=1)
    hot_videos = videos.sort('hotness', ascending=False).video_id.tolist()
    users_history = behaviors.groupby('user_id',as_index=False).agg(lambda x: ' '.join(x.video_id)).drop('score', 1)
    def hot_videos_unwatched(row): 
        try:
            watched = set([item for item in row['video_id'].split()])
            return [x  for x in hot_videos if x not in watched]
        except: # never watched anything
            return hot_videos
    users_history['hot_videos_unwatched'] = users_history.apply(hot_videos_unwatched, axis=1)
    users_hot_videos =users_history.drop('video_id',1)
    return (users_hot_videos,hot_videos)

def combined_scores(behaviors,videos_matrix,hot_videos):
    """ To combine all similar score of all moviews calculated based on user history.
        Result will be each user and his / her top 3 recommendations (if available)
        >>> user_combined_scores = combined_scores(behaviors,videos_matrix)
        >>> user_combined_scores[:3]
                       recommendations  user_id
        user_id                                
        23183    [TV004, TV177, TV461]    23183
        169261          [TV462, TV004]   169261
        762169   [TV004, TV177, TV461]   762169
    """
    # remove videos not in top 20
    videos_matrix = videos_matrix[[x in hot_videos[:20] for x in videos_matrix['video_id_right']]]
    user_history_videos_matrix = pd.merge(behaviors, videos_matrix, left_on=['video_id'], right_on=['video_id_left'])
    def weighted_sim_combined(row):
        return weight_scores[row['score']-1] * row['sim_combined']
    user_history_videos_matrix['weighted_sim_combined'] = user_history_videos_matrix.apply(weighted_sim_combined, axis=1)
    user_history_videos_matrix = user_history_videos_matrix.drop('score', 1)
    user_history_videos_matrix = user_history_videos_matrix.drop('video_id_left', 1)
    user_history_videos_matrix = user_history_videos_matrix.drop('sim_combined', 1)
    user_combined_scores = user_history_videos_matrix.groupby(['user_id', 'video_id_right'],as_index=False).aggregate(np.sum)
    # filter out videos user have watched
    behaviors = behaviors.drop('score', 1)
    grouped_behaviors = pd.DataFrame({ 'video_ids' : behaviors.groupby('user_id').apply(lambda x: list(x.video_id))}) # user_id, list_of_video_ids
    grouped_behaviors['user_id'] = grouped_behaviors.index
    user_combined_scores = pd.merge(user_combined_scores, grouped_behaviors, on=['user_id'])
    user_combined_scores = user_combined_scores[user_combined_scores.apply(lambda x: x['video_id_right'] not in x['video_ids'], axis=1)]
    user_combined_scores = user_combined_scores.drop('video_ids', 1) # user_id, video_id_right, weighted_sim_combined
    # produce result: user - top 3 videos (one entry per user)
    user_combined_scores = user_combined_scores.sort(['weighted_sim_combined'], ascending=False).groupby('user_id').head(3)
    user_combined_scores = pd.DataFrame({ 'recommendations' : user_combined_scores.groupby('user_id').apply(lambda x: list(x.video_id_right))})
    user_combined_scores['user_id'] = user_combined_scores.index
    return user_combined_scores

def processing_recommendations(user_combined_scores,users_hot_videos,hot_videos):
        # separated by '-1,DEXTRA' and '-2,DEXTRA' (removed, otherwise we can't use `row['count'] % 3` below)
    test1 = pd.read_csv('./data/20150701094451-Sample_submission-p1.csv')
    test2 = pd.read_csv('./data/20150701094451-Sample_submission-p2.csv')
    # merge to preserve ordering of the test sets
    submit1 = pd.merge(test1, user_combined_scores, on=['user_id'], how='left')
    submit1 = pd.merge(submit1, users_hot_videos, on=['user_id'], how='left')
    submit1['count'] = submit1.index
    submit2 = pd.merge(test2, user_combined_scores, on=['user_id'], how='left')
    submit2 = pd.merge(submit2, users_hot_videos, on=['user_id'], how='left')
    submit2['count'] = submit2.index
    def recommendation(row):
        try:
            if len(row['recommendations']) == 3: # If we have enough recommendations
                return row['recommendations'][row['count'] % 3]
            else: # welp, not enough
                return row['hot_videos_unwatched'][row['count'] % 3]
        except: # row['recommendations'] could be NaN
            try: # see if there is any `hot_videos_unwatched` available for the user
                return row['hot_videos_unwatched'][row['count'] % 3]
            except: # when user haven't watched anything - no record in behaviors file.
                return hot_videos[row['count'] % 3]
    submit1['video_id'] = submit1.apply(recommendation, axis=1)
    submit2['video_id'] = submit2.apply(recommendation, axis=1)
    submit1 = submit1.drop(['recommendations','count','hot_videos_unwatched'], 1)
    submit2 = submit2.drop(['recommendations','count','hot_videos_unwatched'], 1)
    return (submit1,submit2)

def output_result_to_csv(submit1,submit2):
    print "=> Writing result to CSV"
    print datetime.datetime.now()
    if not os.path.exists('result/'):
        os.makedirs('result/')
    with open('./result/submit-'+'-'.join(str(x) for x in weight_features)+'-'+'-'.join(str(x) for x in weight_scores)+'.csv', 'w') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(submit1.columns)
        writer.writerows(submit1.values)
        writer.writerow(['-1','DEXTRA'])
        writer.writerows(submit2.values)
        writer.writerow(['-2','DEXTRA'])

def main():
    print "=> Processing data - " + str(datetime.datetime.now())
    (behaviors, videos, videos_matrix) = read_data()
    print "=> Calculating hot videos for each user - " + str(datetime.datetime.now())
    (users_hot_videos,hot_videos) = unwatched_hot_videos(behaviors, videos)
    print "=> Combining results - " + str(datetime.datetime.now())
    user_combined_scores = combined_scores(behaviors,videos_matrix,hot_videos)
    print "=> Processing recommendations - " + str(datetime.datetime.now())
    (submit1,submit2) = processing_recommendations(user_combined_scores,users_hot_videos,hot_videos)
    print "=> Output to csv - " + str(datetime.datetime.now())
    output_result_to_csv(submit1,submit2)

if __name__ == "__main__":
    main()