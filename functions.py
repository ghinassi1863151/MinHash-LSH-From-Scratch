#############################################################################    
############################## IMPORTS ######################################
#############################################################################

# Import libraries
import numpy as np      
import scipy.io.wavfile 
import subprocess
import librosa
import librosa.display
import IPython.display as ipd
from random import shuffle
import pandas as pd
from pathlib import Path, PurePath   
from tqdm import tqdm
import pickle as pickle

#############################################################################    
########################## GLOBAL VARIABLES #################################
#############################################################################

# List of absolute paths to open and read files
PATH_TEST_QUERY = "./query/track" 
PATH_ALL_LIST = "all.list"
PATH_SONGS_FOLDER = "./wav/"
PATH_SHINGLES_FILE_ROUNDED = "./pickles/shingles_numpy_rounded.pickle"
PATH_DICT_FILE_ROUNDED = "./pickles/song_peaks_rounded.pickle"
PATH_MATRIX_ROUNDED = "./pickles/matrix_rounded.pickle"

# Define absolute "tune parameters"
N_TRACKS = 1413
DURATION = 15
HOP_SIZE = 512
OFFSET = 1.0
THRESHOLD = 0.2
nperm = 20

# Methods to save and read a ".pickle" file
def save_pickle(element, path):
    with open(f"{path}", 'wb') as f:
        pickle.dump(element, f, pickle.HIGHEST_PROTOCOL)

def load_pickle(path):
    with open(f"{path}", 'rb',) as f:
        return pickle.load(f)
    
#############################################################################    
########################## SONG PREPROCESSING ###############################
#############################################################################

# Methods from "AudioSignals.ipynb" file
def convert_mp3_to_wav(audio:str) -> str:  
    """Convert an input MP3 audio track into a WAV file.

    Args:
        audio (str): An input audio track.

    Returns:
        [str]: WAV filename.
    """
    if audio[-3:] == "mp3":
        wav_audio = audio[:-3] + "wav"
        if not Path(wav_audio).exists():
                subprocess.check_output(f"ffmpeg -i {audio} {wav_audio}", shell=True)
        return wav_audio
    
    return audio

def plot_spectrogram_and_peaks(track:np.ndarray, sr:int, peaks:np.ndarray, onset_env:np.ndarray) -> None:
    """Plots the spectrogram and peaks 

    Args:
        track (np.ndarray): A track.
        sr (int): Aampling rate.
        peaks (np.ndarray): Indices of peaks in the track.
        onset_env (np.ndarray): Vector containing the onset strength envelope.
    """
    times = librosa.frames_to_time(np.arange(len(onset_env)),
                            sr=sr, hop_length=HOP_SIZE)

    plt.figure()
    ax = plt.subplot(2, 1, 2)
    D = librosa.stft(track)
    librosa.display.specshow(librosa.amplitude_to_db(np.abs(D), ref=np.max),
                            y_axis='log', x_axis='time')
    plt.subplot(2, 1, 1, sharex=ax)
    plt.plot(times, onset_env, alpha=0.8, label='Onset strength')
    plt.vlines(times[peaks], 0,
            onset_env.max(), color='r', alpha=0.8,
            label='Selected peaks')
    plt.legend(frameon=True, framealpha=0.8)
    plt.axis('tight')
    plt.tight_layout()
    plt.show()

def load_audio_peaks(audio, offset, duration, hop_size):
    """Load the tracks and peaks of an audio.

    Args:
        audio (string, int, pathlib.Path or file-like object): [description]
        offset (float): start reading after this time (in seconds)
        duration (float): only load up to this much audio (in seconds)
        hop_size (int): the hop_length

    Returns:
        tuple: Returns the audio time series (track) and sampling rate (sr), a vector containing the onset strength envelope
        (onset_env), and the indices of peaks in track (peaks).
    """
    try:
        track, sr = librosa.load(audio, offset=offset, duration=duration)
        onset_env = librosa.onset.onset_strength(track, sr=sr, hop_length=hop_size)
        peaks = librosa.util.peak_pick(onset_env, 10, 10, 10, 10, 0.5, 0.5)
    except Error as e:
        print('An error occurred processing ', str(audio))
        print(e)

    return track, sr, onset_env, peaks


def extract_peaks(song_path, rounded = False):
    
    song_peaks = {}
    if rounded == True:
        for song in tqdm(song_path):
            tmp1, tmp2, onset, peaks = load_audio_peaks(PATH_SONGS_FOLDER+song, OFFSET, DURATION, HOP_SIZE)
            song_peaks[' '.join(song.split('/')[-1][3:-4].split('_')).lower() + ' - ' + ' '.join(song.split('/')[0].split('_'))] = np.array(onset[peaks]).round(1)
    else:
        for song in tqdm(song_path):
            tmp1, tmp2, onset, peaks = load_audio_peaks(PATH_SONGS_FOLDER+song, OFFSET, DURATION, HOP_SIZE)
            song_peaks[' '.join(song.split('/')[-1][3:-4].split('_')).lower() + ' - ' + ' '.join(song.split('/')[0].split('_'))] = np.array(onset[peaks])
            
    return song_peaks


#############################################################################    
################################# HASHING ###################################
#############################################################################

# This function takes in input the dictionary {song: list of peaks} and return a list of all unique shingles (peaks values) founded in all song peaks. 
def unique_shingles(song_peaks):    
    
    tot_shingles = list(song_peaks.values())

    shingles = []
    for i in tqdm(tot_shingles):
        shingles.append(i)

    shingles = np.hstack(shingles)
    shingles = np.array(list(dict.fromkeys(shingles))) # all unique peaks

    return shingles

# This method return a vector of ones and zeros. It puts one if the song contains the peak, otherwise zero.
def onehot(peaks, shingles):
    return np.array([1 if x in peaks else 0 for x in shingles])


# This function will return a matrix which has as rows the shingles and as columns the songs titles
def shingles_matrix(shingles, song_peaks):
    
    matrix = np.zeros(len(shingles))
    
    for v in tqdm(list(song_peaks.values())):
        matrix = np.vstack([matrix, onehot(v, shingles)])

    matrix = np.delete(matrix, (0), axis=0)
    
    return matrix

# This function apply the "MinHash" algorithm given in input the matrix generated with the previous function, the disctionary {song: list of peaks}, the list of all shingles.
def hash_matrix(matrix, shingles, song_peaks):

    # we transpose the matrix in order to have the shingles on the rows and the songs on the columns
    df = pd.DataFrame(matrix.transpose(), index = range(len(shingles)), columns = list(song_peaks.keys()))

    hash_matrix = np.zeros(len(song_peaks), dtype = int)
    
    # we permutate the rows of the matrix and for each column we look at the first non-zero value and store in a list
    # the corresponing raw index of that value, then by stacking the list at each permutation we get back the hash matrix
    for i in tqdm(range(nperm)):
        hash_matrix = np.vstack([hash_matrix, list(df.sample(frac = 1, random_state = i).reset_index(drop=True).ne(0).idxmax())])
        # .sample shuffles all the rows of the matrix
        # .ne(x) looks for the values different from x
        # .idxmax finds the first index between all the indexes with non-zero values

    hash_matrix = np.delete(hash_matrix, (0), axis=0)
    hash_mat = pd.DataFrame(hash_matrix, index = range(1, nperm + 1), columns = list(song_peaks.keys()))
    
    return hash_mat



#############################################################################    
################################# LSH & QUERY ###############################
#############################################################################

# Method to generate fingerprint for a given query song. If the parameter rounded is set to True, the fingerprints generated will be calculated on rounded peaks.
def fingerprint(query, shingles, rounded=False):
    _, _, onset_q, peaks_q = load_audio_peaks(query, OFFSET, DURATION, HOP_SIZE)

    query_oh = onehot(np.array(onset_q[peaks_q]).round(1), shingles)
    
    query_df = pd.DataFrame(query_oh.transpose(), index = range(len(shingles)), columns = ['query'])
    
    hash_query = np.zeros(1, dtype = int)
    for i in range(nperm):
        hash_query = np.vstack([hash_query, list(query_df.sample(frac = 1, random_state = i).reset_index(drop=True).ne(0).idxmax())])
        
    hash_query = np.delete(hash_query, (0), axis=0)
    hash_query = pd.DataFrame(hash_query, index = range(nperm), columns = ['query'])
    
    return hash_query

# This function will generate the buckets from the hash matrix generated and takes as input also the desired number of bands.
def db_buckets(hash_matrix, n_bands):
    
    # first we have to decide a number of bands that is a divisor of the signature length in order to have equal slices of the signature
    # of course the less bands we use the more discriminant the LSH will be
    rows = int(nperm/n_bands)
    buckets = {}
    
    for song_name, song_hash in hash_matrix.iteritems():
        song_hash = list(song_hash) # convert the columns of the dataframe from pandas series into lists
        
        for i in range(0, len(song_hash), rows):
            bucket_hash = tuple(song_hash[i : i + rows]) # the hash of the bucket will be a tuple with number of elements = rows
            
            if bucket_hash in buckets:
                buckets[bucket_hash].add(song_name) # if we already encountered that band we only add the song name
            else:
                buckets[bucket_hash] = {song_name} # otherwise we create a new key:value
                
    return buckets

# This function will split the fingerprint of the query in bands
def query_buckets(fingerprint, n_bands):
    
    # same as before but in this case fingerprint is a list and not a dataframe
    
    rows = int(len(fingerprint)/n_bands) 
    
    # splitting the signature in nbands subvectors
    q_buckets = {}
    for i in range(0, len(fingerprint), rows):
        q_buckets[tuple(fingerprint[i : i + rows])] = 'query'
        
    return q_buckets

# This function will apply the LSH algorithm to a query as input, given alse the database of songs, a list of all possible shingles and the buckets generated from the database
def shazamLSH(query, database, shingles, buckets):
    
    print('Im listening to your music, please dont make noise ...')
    
    score = (0, '')
    db_keys = list(database.keys())
    buckets_keys = list(buckets.keys())
    
    query_fingerprint = list(fingerprint(query, shingles, rounded=True)['query'])
    query_bands = query_buckets(query_fingerprint, 5)
    query_keys = list(query_bands.keys())
    
    # we compute the intersection between the query buckets and the database buckets
    common_bands = set(query_bands).intersection(set(buckets_keys))
    
    # we compute the jaccard only with the songs in the buckets of the intersection
    for band in common_bands:
        for song in buckets[band]:
            jac = Jaccard(query_fingerprint, database[song])
            if score < (jac, song): 
                score = (jac, song)    # store the maximum score   
     
    print('Maybe you were looking for this song: ', score[1], '\n-----------------------\n')