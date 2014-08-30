'''
Created on Aug 27, 2014

@author: abhinav2
'''
import tornado
from Constants import *
import HelperFunctions
import json

quizWaitingConnectionsPool = {}#based on type_of quiz we have the waiting pool
runningQuizes = {} # all currently running quizes in this server
def GenerateProgressiveQuizClass(dbUtils, responseFinish , userAuthRequired):
    
    def generateProgressiveQuiz(quizId , uids):
        quiz = dbUtils.getQuizDetails(quizId).get(0)
        if(quizId):
            nQuestions = quiz.nQuestions
        else:
            nQuestions = 7
        
        questions = dbUtils.getRandomQuestions(quiz)
        id = HelperFunctions.generateKey(10)
        userStates={}
        for i in uids:
            userStates[i]={}
            
        runningQuizes[id] = quizState = {   QUESTIONS: questions,
                                            CURRENT_QUESTION :-1,
                                            N_CURRENT_QUESTION_ANSWERED:[],
                                            USERS:userStates##{uid:something}
                                        }
        return id , quizState
    
    
    
    
            
    class ProgressiveQuizHandler(tornado.websocket.WebSocketHandler):
        quizPoolWaitId = None   
        uid = None
        quizConnections =None
        runningQuizId= None
        runningQuiz = None
        
        def broadcastToGroup(self, message, allClients):
            for i in allClients:
                if(i!=self):
                    i.write_message(message)
    
        def broadcastToAll(self, message, allClients):
            for i in allClients:
                i.write_message(message)
    
        
        
        @userAuthRequired
        def open(self, user = None):
            runningQuizId = self.get_argument("isRunningQuiz",None)
            isChallenge = self.get_argument("isChallenge",None)
            isChallenged = self.get_argument("isChallenged",None)
            quizId = self.get_argument("quizId")
            if(runningQuizId):
                pass
            
            self.quiz = quiz = dbUtils.getQuizDetails(quizId)
            self.quizPoolWaitId =  quizPoolWaitId = "_".join(quiz.tags)+"_"+str(quiz.nPeople)
            self.user = user
            if(isChallenge!=None):
                self.quizPoolWaitId+="_"+quizId+"_"+self.user.uid   
            elif(isChallenged!=None):
                self.quizPoolWaitId+="_"+quizId+"_"+isChallenged
                
            quizConnections = quizWaitingConnectionsPool.get(quizPoolWaitId,None)
            if(quizConnections):
                quizConnections.append(self)
            else:
                 quizConnections = quizWaitingConnectionsPool[quizPoolWaitId] = [self]
            
            self.quizConnections = quizConnections
            if(len(quizConnections)>=int(quiz.nPeople)):# we have enough people
                self.quizConnections = [quizConnections.pop() for i in range(0, quiz.nPeople)]#nPeople into current quiz
                uids = map(lambda x:x.user.to_short_json() , quizConnections)
                self.runningQuizId , self.runningQuiz = generateProgressiveQuiz(quiz, uids)
                #question_one = self.runningQuiz[QUESTIONS][0]
                self.broadcastToAll({"messageType":STARTING_QUESTIONS,
                                                   "payload":self.runningQuizId,
                                                   "payload1":"["+",".join(map(lambda uid:dbUtils.getUserByUid(uid).to_json() , uids))+"]",
                                                   "payload2":"["+",".join(map(lambda x:x.to_json() ,dbUtils.getRandomQuestions(self.quiz)))+"]"
                                                  },
                                quizConnections
                               )
        # the client sent the message
        def on_message(self, message):
            print message
            userQuizUpdate = json.loads(message)
            messageType = int(userQuizUpdate[MESSAGE_TYPE])
            if(messageType==USER_ANSWERED_QUESTION):
                questionId = userQuizUpdate[QUESTION_ID]
                userAnswer = userQuizUpdate[USER_ANSWER]
                whatUserGot = userQuizUpdate[WHAT_USER_HAS_GOT]
                self.broadcastToAll({"messageType":USER_ANSWERED_QUESTION,"payload":whatUserGot,"payload1":questionId},self.quizConnections)
                self.runningQuiz[N_CURRENT_QUESTION_ANSWERED].append(self.uid)
                if(len(self.runningQuiz[N_CURRENT_QUESTION_ANSWERED])==len(self.quizConnections)):#if everyone aswered
                    self.runningQuiz[N_CURRENT_QUESTION_ANSWERED]=[]
                    currentQuestion = self.runningQuiz[CURRENT_QUESTION]
                    self.runningQuiz[CURRENT_QUESTION]=currentQuestion+1
                    if(currentQuestion>=self.quiz.nQquestions):
                        self.broadcastToAll({"messageType":ANNOUNCING_WINNER,
                                               "payload":json.dumps(self.runningQuiz[USERS])
                                            },
                                         self.quizConnections)
                        #TODO: calculate winner and save in Db
                        return
                    currentQuestionIndex = self.runningQuiz[CURRENT_QUESTION]
                    question = self.runningQuiz[QUESTIONS][currentQuestionIndex]
                    self.broadcastToAll({"messageType":NEXT_QUESTION,
#                                            "payload":question.to_json(),
                                          },
                                     self.quizConnections)
                
            elif(messageType==GET_NEXT_QUESTION):#user explicitly calls this function on if other doesn't responsd
                n_answered =self.runningQuiz[N_CURRENT_QUESTION_ANSWERED]
                isFirstQuestion = False
                if(self.runningQuiz[CURRENT_QUESTION]==-1):
                    isFirstQuestion = True
                    self.runningQuiz[CURRENT_QUESTION]==0
                    
                if(isFirstQuestion or len(n_answered) ==len(self.quizConnections)):#if everyone aswered
                    self.runningQuiz[N_CURRENT_QUESTION_ANSWERED]=[]
                    currentQuestionIndex = self.runningQuiz[CURRENT_QUESTION]
                    question = self.runningQuiz[QUESTIONS][currentQuestionIndex]
                    self.broadcastToAll({"messageType":NEXT_QUESTION,
                                           "payload":question.to_json(),
                                          },
                                     self.quizConnections
                                  )
                else:
                    #some state to clean TODO
                    pass
                # client disconnected
            elif(messageType==ACTIVATE_BOT):
                self.write_message(json.dumps({"messageType":OK_ACTIVATING_BOT,"payload": dbUtils.getBotUser().toJson(), 
                                               "payload1":"["+",".join(map(lambda x:x.to_json() ,dbUtils.getRandomQuestions(self.quiz)))+"]"}))
                #THEN CLIENT CLOSES CONNECTION
                
        def on_close(self):
            self.broadcastToGroup({"messageType":USER_DISCONNECTED,"payload1":self.user.uid},self.quizConnections)
            self.quizConnections.remove(self)#either waiting or something , we don't care
            if(len(self.quizConnections)):
                del runningQuizes[self.runningQuizId]

        
    return ProgressiveQuizHandler