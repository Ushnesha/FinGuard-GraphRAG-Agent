from load_data import load_finqa_corpus

FinQA_data_path = "data/FinQA/train.json"
FinQA_corpus = load_finqa_corpus(FinQA_data_path)

MEGA_CORPUS = [{"CORPUS" : FinQA_corpus[10:20],
"QUERY" : ["What was the percentage increase in total aircraft fuel expense for mainline and regional operations from 2016 to 2018?", "By what percentage did Intel Corporation's total cash and investments grow from December 29, 2012 to December 28, 2013?", "What is the total estimated value (in thousands of dollars) of the restricted stock and restricted stock units granted to employees during the fiscal year ended March 31, 2012?","What is the net difference in the fair value of forward exchange contracts between October 31, 2009, and November 1, 2008, under a scenario of a 10\% unfavorable movement in foreign currency exchange rates?", "In fiscal 2019, what percentage of the net cash provided by operating activities was spent on the purchases of land, buildings, and equipment?"]}]