from flask import Flask, escape, request, send_file
import sqlite3
from datetime import datetime
import os
import json


app = Flask(__name__)

conn = sqlite3.connect('site.db')
cursor = conn.cursor()
# create scantrons database
cursor.execute('''
    CREATE TABLE IF NOT EXISTS scantrons (
        scantron_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        subject TEXT,
        score INTEGER,
        actual TEXT,
        expected TEXT,
        created_at TEXT
    )
''')
conn.commit()

# create tests database
cursor.execute('''
    CREATE TABLE IF NOT EXISTS tests (
        test_id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT,
        answer_keys TEXT,
        submissions TEXT,
        created_at TEXT
    )
''')
conn.commit()


@app.route('/')
def hello():
    name = request.args.get("name", "World")
    return f'Hello, {escape(name)}!'

@app.route('/api/tests/', methods=['POST'])
def createTest():
    req = request.json
    subject = req['subject']
    submissions = ''
    answerKeysDict = req['answer_keys']
    answerKeysString = json.dumps(answerKeysDict)
    now = str(datetime.now())

    result = {}
    with sqlite3.connect('site.db') as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()

        # insert new test into table
        cursor.execute("INSERT INTO tests (subject, answer_keys, submissions, created_at) VALUES (?,?,?,?)", (subject, answerKeysString, submissions, now))
        conn.commit()

        # get back newly made test to get its ID
        cursor.execute("SELECT * FROM tests WHERE (subject=? AND answer_keys=? AND created_at=?)", (subject, answerKeysString, now))
        result = cursor.fetchone()
        result['answer_keys'] = answerKeysDict
        result['submissions'] = []
        del result['created_at']

    return result, 201

@app.route('/api/tests/<id>/scantrons', methods=['POST'])
def uploadScantron(id):    
    result = {}
    scantronID = None

    dataInBytes = None
    # if file sent using postman
    if(request.data != b''):
        dataInBytes = request.data
    # if file sent using curl
    else:
        dataInBytes = request.files['data'].read()
    dataObject = dataInBytes.decode('utf-8')
    dataObject = json.loads(dataObject)

    name = dataObject['name']
    subject = dataObject['subject']
    score = 0
    actualAnswersDict = dataObject['answers']
    actualAnswersString = json.dumps(actualAnswersDict)
    now = str(datetime.now())

    with sqlite3.connect('site.db') as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM tests WHERE test_id=?", id)
        data = cursor.fetchone()
        expectedAnswersString = data['answer_keys']
        expectedAnswersDict = json.loads(expectedAnswersString)
        score = calculateScore(expectedAnswersDict, actualAnswersDict)

        # create new scantron entry 
        cursor.execute("INSERT INTO scantrons (name, subject, score, actual, expected, created_at) VALUES (?,?,?,?,?,?)", (name, subject, score, actualAnswersString, expectedAnswersString, now))
        conn.commit()

        # retrieve newly made scantron entry to get it's ID
        cursor.execute("SELECT * FROM scantrons WHERE (subject=? AND name=? AND created_at=?)", (subject, name, now))
        result = cursor.fetchone()

        scantronID = result['scantron_id']
        result['scantron_url'] = "http://localhost:5000/files/"+str(scantronID)+".json"
        
        temp = {}
        expectedAnsDict = json.loads(result['expected'])
        actualAnsDict = json.loads(result['actual'])
        for key in expectedAnsDict.keys():
            temp[key] = {
                "actual": actualAnsDict[key],
                "expected": expectedAnsDict[key]
            }
        result['results'] = temp

        del result['created_at']
        del result['expected']
        del result['actual']

        # add new scantron ID to the test submissions
        cursor.execute("SELECT * FROM tests WHERE test_id=?", id)
        data = cursor.fetchone()
        oldSubmissions = data['submissions']
        oldSubmissions += ','
        updatedSubmissions = oldSubmissions + str(scantronID)
        cursor.execute("UPDATE tests SET submissions=? WHERE test_id=?", (updatedSubmissions, id))
        conn.commit()

    fl = open('files/' + str(scantronID) + '.json', 'wb')
    fl.write(dataInBytes)
    fl.close()

    return result, 201

@app.route('/api/tests/<id>', methods=['GET'])
def getTest(id):
    result = {}
    with sqlite3.connect('site.db') as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tests WHERE test_id=?', id)
        result = cursor.fetchone()

        if(result == None):
            return "No test with id "+id

        del result['created_at']
        result['answer_keys'] = json.loads(result['answer_keys'])

        # get scantrons from scantron table
        result['submissions'] = result['submissions'][1:]   #remove comma from front
        if not result['submissions']:
            result['submissions'] = []
        else:
            newSubmissions = []
            allSubmissions = result['submissions'].split(',')
            for scanID in allSubmissions:
                temp = getScantron(scanID, cursor)
                newSubmissions.append(temp)
            result['submissions'] = newSubmissions

    return result

@app.route('/files/<id>.json')
def returnFile(id):
    f = str(id) + '.json'
    for filename in os.listdir('files'):
        if(filename == f):
            return send_file('files/'+filename)
    response = 'No scantron with ID '+id
    return response


# helper functions

def dict_factory(cursor, row):
    d = {}
    for idx,col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def getScantron(scanID, cursor):
    result = {}
    cursor.execute('SELECT * FROM scantrons WHERE scantron_id=?',scanID)
    result = cursor.fetchone()

    temp = {}
    expectedAnsDict = json.loads(result['expected'])
    actualAnsDict = json.loads(result['actual'])
    for key in expectedAnsDict.keys():
        temp[key] = {
            "actual": actualAnsDict[key],
            "expected": expectedAnsDict[key]
        }
    result['results'] = temp
    result['scantron_url'] = "http://localhost:5000/files/"+str(result['scantron_id'])+".json"
    del result['created_at']
    del result['expected']
    del result['actual']

    return result

def calculateScore(expected, actual):
    score = len(expected)
    for key in expected.keys():
        # format validation for scantron answers
        if(isinstance(actual[key], str)):
            if(actual[key] != expected[key]):
                score -= 1
    return score
