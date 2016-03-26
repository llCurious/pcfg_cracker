#!/usr/bin/env python3

########################################################################################
#
# Name: PCFG_Cracker "Next" Function
# Description: Section of the code that is responsible of outputting all of the
#              pre-terminal values of a PCFG in probability order.
#              Because of that, this section also handles all of the memory management
#              of a running password generation session
#
#########################################################################################


import sys   #--Used for printing to stderr
import string
import struct
import os
import types
import time
import queue
import copy
import heapq


from sample_grammar import s_preterminal
from pcfg_manager.ret_types import RetType

###################################################################################################
# Used to hold the parse_tree of a path through the PCFG that is then stored in the priority queue
###################################################################################################
class QueueItem:
    
    ############################################################################
    # Basic initialization function
    ############################################################################
    def __init__(self, is_terminal = False, probability = 0.0, parse_tree = []):
        self.is_terminal = is_terminal      ##-Used to say if the parse_tree has any expansion left or if all the nodes represent terminals
        self.probability = probability    ##-The probability of this queue items
        self.parse_tree = parse_tree        ##-The actual parse through the PCFG that this item represents
        
    ##############################################################################
    # Need to have a custom compare functions for use in the priority queue
    # Really annoying that I have to do this the reverse of what I'd normally expect
    # since the priority queue will output stuff of lower values first.
    # Aka if there are two items with probabilities of 0.7 and 0.4, the PQueue will
    # by default output 0.4 which is ... not what I'd like it to do
    ##############################################################################
    def __lt__(self, other):
        return self.probability > other.probability
    
    def __le__(self, other):
        return self.probability >= other.probability
        
    def __eq__(self, other):
        return self.probability == other.probability
        
    def __ne__(self, other):
        return self.probability != other.probability
        
    def __gt__(self, other):
        return self.probability < other.probability
        
    def __ge__(self, other):
        return self.probability <= other.probability
    
    ###############################################################################
    # Overloading print operation to make debugging easier
    ################################################################################
    def __str__(self):
        ret_string = "isTerminal = " + str(self.is_terminal) + "\n"
        ret_string += "Probability = " + str(self.probability) + "\n"
        ret_string += "ParseTree = " + str(self.parse_tree) + "\n"
        return ret_string
        
    #################################################################################
    # A more detailed print that is easier to read. Requires passing in the pcfg
    #################################################################################
    def detailed_print(self,pcfg):
        ret_string = "isTerminal = " + str(self.is_terminal) + "\n"
        ret_string += "Probability = " + str(self.probability) + "\n"
        ret_string += "ParseTree = "
        ret_string += pcfg.print_parse_tree(self.parse_tree)
        return ret_string
        
    
            
#######################################################################################################
# I may make changes to the underlying priority queue code in the future to better support
# removing low probability items from it when it grows too large. Therefore I felt it would be best
# to treat it as a class. Right now though it uses the standared python queue HeapQ as its
# backend
#######################################################################################################
class PcfgQueue:
    ############################################################################
    # Basic initialization function
    ############################################################################
    def __init__(self):
        self.p_queue = []  ##--The actual priority queue
        self.max_probability = 1.0 #--The current highest priority item in the queue. Used for memory management and restoring sessions
        self.min_probability = 0.0 #--The lowest prioirty item is allowed to be in order to be pushed in the queue. Used for memory management
        self.max_queue_size = 500000 #--Used for memory management. The maximum number of items before triming the queue. (Note, the queue can temporarially be larger than this)
        self.reduction_size = self.max_queue_size // 4  #--Used to reduce the p_queue by this amount when managing memory

    #############################################################################
    # Push the first value into the priority queue
    # This will likely be 'START' unless you are constructing your PCFG some other way
    #############################################################################
    def initialize(self, pcfg):
        index = pcfg.start_index()
        if index == -1:
            print("Could not find starting position for the pcfg")
            return RetType.GRAMMAR_ERROR
        
        q_item = QueueItem(is_terminal=False, probability = pcfg.find_probability([index,0,[]]), parse_tree = [index,0,[]])
        heapq.heappush(self.p_queue,q_item)
        
        return RetType.STATUS_OK
 
    ###############################################################################
    # Memory managment function to reduce the size of the priority queue
    # This is *hugely* wasteful right now. On my todo list is to modify the
    # p_queue code to allow easier deletion of low priority items
    ###############################################################################
    def trim_queue(self):
        keep_list = []
        orig_size = len(self.p_queue)
        
        ##---Pop the top 1/2 of the priority queue off and save it ---##
        #for index in range(0,(self.max_queue_size//2)):
        for index in range(0,self.max_queue_size-self.reduction_size):
            item = heapq.heappop(self.p_queue)
            heapq.heappush(keep_list,item)
            #if index == (self.max_queue_size//2)-1:
            if index == (self.max_queue_size-self.reduction_size)-1:
                ###--- Save the probability of the lowest priority item on the new Queue
                self.min_probability = item.probability
                print("min prob: " + str(self.min_probability), file=sys.stderr)
                ###--- Copy all items of similar probabilities over so everything dropped is lower probability
                item = heapq.heappop(self.p_queue)
                while item.probability == self.min_probability:
                    heapq.heappush(keep_list,item)
                    item = heapq.heappop(self.p_queue)
                    
        ##--Now copy the top 1/2 of the priority queue back----##
        self.p_queue = copy.deepcopy(keep_list)

        ##--The grammar would have to be pretty weird for this sanity check to fail, but it's better to check
        ##--since weirdness happens
        if orig_size == len(keep_list):
            return RetType.QUEUE_FULL_ERROR
        return RetType.STATUS_OK
        
     
    ###############################################################################
    # Used to restore the priority queue from a previous state
    # Allows resuming paused, (or crashed), sessions and is used in the memory management
    ###############################################################################
    def rebuild_queue(self,pcfg):
        print("Rebuilding p_queue", file=sys.stderr)
        self.p_queue = []
        rebuild_list = []
        self.min_probability = 0.0
        
        index = pcfg.start_index()
        if index == -1:
            print("Could not find starting position for the pcfg")
            return RetType.GRAMMAR_ERROR
            
        rebuild_list.append(QueueItem(is_terminal=False, probability = 1.0, parse_tree = [index,0,[]]))
        while len(rebuild_list) != 0:
            q_item = rebuild_list.pop(0)
            ret_list = self.rebuild_from_max(pcfg,q_item)
            if len(self.p_queue) > self.max_queue_size:
                print("trimming Queue", file=sys.stderr)
                self.trim_queue()
                print("done", file=sys.stderr)
            for item in ret_list:
                rebuild_list.append(item)
                
        print("Done", file=sys.stderr)
        return RetType.STATUS_OK    
        
    #########################################################################################################
    # Used for memory management. I probably should rename it. What this function does is
    # determine whether to insert the item into the p_queue if it is lower probability than max_probability
    # or returns the item's children if it is higher probability than max_probability    
    #########################################################################################################
    def rebuild_from_max(self,pcfg,q_item):
        ##--If we potentially want to push this into the p_queue
        if q_item.probability <= self.max_probability:
            ##--Check to see if any of it's parents should go into the p_queue--##
            parent_list = pcfg.findMyParents(q_item.parse_tree)
            for parent in parent_list:
                ##--The parent will be inserted in the queue so do not insert this child--##
                if pcfg.find_probability(parent) <=self.max_probability:
                    return []
            ##--Insert this item in the p_queue----##
            if q_item.probability >= self.min_probability:
                heapq.heappush(self.p_queue,q_item) 
            return []
            
        ##--Else check to see if we need to push this items children into the queue--##
        else:
            children_list = pcfg.find_children(q_item.parse_tree)
            my_children_list = self.find_my_children(pcfg,q_item,children_list)
            ret_list = []
            for child in my_children_list:
                ret_list.append(QueueItem(is_terminal = pcfg.find_is_terminal(child), probability = pcfg.find_probability(child), parse_tree = child))
            return ret_list
     

    ###########################################################################
    # Given a list of children, find all the children who this parent should
    # insert into the list for rebuilding the queue
    ###########################################################################
    def find_my_children(self,pcfg,q_item,children_list):
        my_children = []
        ##--Loop through all of the children---##
        for child in children_list:
            ##--Grab all of the potential parents for this child
            parent_list = pcfg.findMyParents(child)
            prob_list = []
            for parent in parent_list:
                prob_list.append((parent,pcfg.find_probability(parent)))
            parent_index = 0
            lowest_prob = prob_list[0][1]
            for index in range(1,len(prob_list)):
                if prob_list[index][1] < lowest_prob:
                    parent_index = index
            
            if prob_list[parent_index][0] == q_item.parse_tree:
                my_children.append(child)
        return my_children
        
    ###############################################################################
    # Pops the top value off the queue and then inserts any children of that node
    # back in the queue
    ###############################################################################
    def next_function(self,pcfg, queue_item_list = []):
        
        ##--Only return terminal structures. Don't need to return parse trees that don't actually generate guesses 
        while True:
            ##--First check if the queue is empty
            while len(self.p_queue) == 0:
                ##--If there was some memory management going on, try to rebuild the queue
                if self.min_probability != 0.0:
                    self.rebuild_queue(pcfg)
                ##--The grammar has been exhaused, exit---##
                else:
                    return RetType.QUEUE_EMPTY
                
            ##--Pop the top value off the stack
            queue_item = heapq.heappop(self.p_queue)
            self.max_probability = queue_item.probability
            ##--Push the children back on the stack
            ##--Currently using the deadbeat dad algorithm as described in my dissertation
            ##--http://diginole.lib.fsu.edu/cgi/viewcontent.cgi?article=5135
            self.deadbeat_dad(pcfg, queue_item)
            
            ##--Memory management
            if len(self.p_queue) > self.max_queue_size:
                print("trimming Queue", file=sys.stderr)
                self.trim_queue()
                print("done", file=sys.stderr)
            ##--If it is a terminal structure break and return it
            if queue_item.is_terminal == True:
                queue_item_list.append(queue_item)
                break

        #print("--Returning this value")
        #print(queue_item_list[0].detailed_print(pcfg), file=sys.stderr)
        return RetType.STATUS_OK

    #################################################################################################################################################
    # The deadbead dad "next" algorithm as described in http://diginole.lib.fsu.edu/cgi/viewcontent.cgi?article=5135
    # In a nutshell, imagine the parse tree as a graph with the 'S' node at top
    # The original "next" function inserted every child parse through it by incrementing the counter by one to the left
    # so the node (1,1,1) would have the children (2,1,1), (1,2,1), and (1,1,2).
    # The child (1,2,1) would only have the children (1,3,1) and (1,2,2) though.
    # This was to prevent any duplicate entries being pushing into the queue
    # The problem was this was *very* memory intensive
    #
    # The deadbeat dad algorithm instead looks at all the potential parents of *every* child node it could create
    # If any of those parents have lower probability than the current node, it "abandons" that child for the other parent to take care of it
    # Only the parent with the lowest probability inserts the child into the queue. That is because that parent knows there are no other parents
    # that will appear later. I know the name is unfortunate, but it really sums up the approach.
    # Basically we're trading computation time for memory. Keeping the queue small though saves computation time too though so
    # in longer runs this approach should be a clear winner compared to the original next function
    # TODO: There is a *TON* of optimization I can do in the current version of this "next" function
    ##################################################################################################################################################
    def deadbeat_dad(self,pcfg, queue_item):
        
        my_children_list = pcfg.deadbeat_dad(queue_item.parse_tree, parent_prob = queue_item.probability)

        ##--Create the actual QueueItem for each child and insert it in the Priority Queue
        for child in my_children_list:
            child_node = QueueItem(is_terminal = pcfg.find_is_terminal(child), probability = pcfg.find_probability(child), parse_tree = child)
            if child_node.probability <= queue_item.probability:
                ##--Memory management check---------
                ##--If the probability of the child node is too low don't bother to insert it in the queue
                if child_node.probability >= self.min_probability:
                    heapq.heappush(self.p_queue,child_node)
            else:
                print("Hmmm, trying to push a parent and not a child on the list", file=sys.stderr)
                
            
###################################################################
# Random Test Function
####################################################################                
def test_queue(pcfg):
    s_queue_item = QueueItem(parse_tree=s_pre_terminal)
    print(s_queue_item, file=sys.stderr)
    print("--------------", file=sys.stderr)
    print(s_queue_item.detailed_print(pcfg), file=sys.stderr)
            
        