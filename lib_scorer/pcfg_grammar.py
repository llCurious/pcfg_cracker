#!/usr/bin/env python3


#############################################################################
# This file contains the functionality to parse raw passwords for PCFGs
#
# The PCFGPasswordParser class is designed to be instantiated once and then
# process one password at at time that is sent to it
#
#############################################################################


import sys
from collections import Counter

# Local imports
from lib_trainer.keyboard_walk import detect_keyboard_walk
from lib_trainer.email_detection import email_detection
from lib_trainer.website_detection import website_detection
from lib_trainer.year_detection import year_detection
from lib_trainer.context_sensitive_detection import context_sensitive_detection
from lib_trainer.alpha_detection import alpha_detection
from lib_trainer.digit_detection import digit_detection
from lib_trainer.other_detection import other_detection
from lib_trainer.base_structure import base_structure_creation
from lib_trainer.multiword_detector import MultiWordDetector


## Responsible for holding the Grammar and evaluating inputs against it
#
class PcfgGrammar:

    ## Initializes the class and all the data structures
    #
    def __init__(self):
        
        ## Information for using this grammar
        #
        self.encoding = None
        
        ## The following counters hold the base grammar
        #
        self.count_keyboard = {}
        self.count_emails = Counter()
        self.count_email_providers = Counter()
        self.count_website_urls = Counter()
        self.count_website_hosts = Counter()
        self.count_website_prefixes = Counter()
        self.count_years = Counter()
        self.count_context_sensitive = Counter()
        self.count_alpha = {}
        self.count_alpha_masks = {}
        self.count_digits = {}
        self.count_other = {}
        self.count_base_structures = Counter()
        self.count_raw_base_structures = Counter()
        
        
    ## Initializes the multiword detector
    #
    def create_multiword_detector(self):
        
        # Minimum length of a word that is part of a multi-word
        min_len = 4
    
        # Create the multi-word detector. Since we'll be training it on base words
        # that have already been extracted, can set the threshold to 1 and only
        # parse words we want to be part of a multiword
        self.multiword_detector = MultiWordDetector(threshold = 1, min_len = min_len)
        
        # Go through all of the alpha strings to register them as potential multi-word values
        for key, value in self.count_alpha.items():
            if key >= min_len:
            
                # Will go through list in reverse order so we can skip the lowest
                # occurence items and not mark them as potential base values for
                # multiwords
                prob_list = reversed(value.most_common())
                
                skipped = 0
                prev_prob = 0.0
                
                for item in prob_list:
                    if skipped < 5:
                        if item[1] > prev_prob:
                            skipped += 1
                            prev_prob = item[1]
                            
                    else:
                        self.multiword_detector.train(item[0])
                    
    
    ## Parses an input value and determines if it is a password or not
    #
    # Will return a tuple of word, category, probability
    #
    # category = [pewo]
    #   -p = password
    #   -e = e-mail
    #   -w = website
    #   -o = other
    #
    def parse(self, password):
    

        
        # Since keyboard combos can look like many other parsings, filter them
        # out first 
        section_list, found_walks = detect_keyboard_walk(password)
        
        found_emails, found_providers = email_detection(section_list)
        found_urls, found_hosts, found_prefixes = website_detection(section_list)
        
        # Identify if e-mails or urls were found
        if found_emails:
            category = 'e'
        elif found_urls:
            category = 'w'
        else:
            category = 'o'
        
        # Bail out early if e-mails or websites were found
        if category in ['e', 'w']:
            return (password, category, 0)
            
        found_years = year_detection(section_list)
        found_context_sensitive_strings = context_sensitive_detection(section_list)
        found_alpha_strings, found_mask_list = alpha_detection(section_list, self.multiword_detector)
        found_digit_strings = digit_detection(section_list)
        found_other_strings = other_detection(section_list)
        is_supported, base_structure = base_structure_creation(section_list)
        
        # Quick bail out if the base structure is not supported
        # This shouldn't happen since we are already bailing out if there are
        # websites or e-mails, but in the future more values may be added
        # that don't translate well
        #
        if not is_supported:
            category = 'o'
            return (password, category, 0)
            
        ## Find the probability for all of the transitions and values
        #
        # Start out at 100% probability
        cur_prob = 1.0
        
        # Note, for the Python counters if a key is not found, it returns abs
        # '0' vs a KeyError exception. Since a probability of 0 is what we
        # are looking for if that happens, that's perfect. This can still
        # throw KeyError exceptoins though for the length indexed counters if
        # no item at that length is found. Therefore we still need to catch
        # KeyErrors
        try:
            for item in found_walks:
                cur_prob *= self.count_keyboard[len(item)][item]
            
            for item in found_years:
                cur_prob *= self.count_years[item]
                
            for item in found_context_sensitive_strings:
                cur_prob *= self.count_context_sensitive[item] 
            
            for item in found_alpha_strings:
                cur_prob *= self.count_alpha[len(item)][item]
                
            for item in found_mask_list:
                cur_prob *= self.count_alpha_masks[len(item)][item]
                
            for item in found_digit_strings:
                cur_prob *= self.count_digits[len(item)][item]
                
            for item in found_other_strings:
                cur_prob *= self.count_other[len(item)][item]
            
            cur_prob *= self.count_base_structures[base_structure]
        
        except KeyError:
            cur_prob = 0
        
        if cur_prob != 0:
            category = 'p'
            
        return (password, category, cur_prob)
                
       
        