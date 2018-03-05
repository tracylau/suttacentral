import regex
import logging
import itertools
from collections import defaultdict

from data_loader.util import numericsortkey, sort_and_groupby
from common.queries import UIDS_IN_ORDER_BY_DIVISION
from common.uid_matcher import UidMatcher



def get_uid_stem(uid):
    """ This suffices for this module """
    return regex.match(r'^[a-z]+', uid)[0]


def further_split_uids(divisions):
    # Split divisions into subdivisions
    # The vast majority of divisions will simply be returned unmodified
    for division_uid, uids_in_division in divisions:
        stems = []
        groups = []
        for stem, group in itertools.groupby(uids_in_division, key=get_uid_stem):
            stems.append(stem)
            groups.append(tuple(group))
        if len(stems) == 1:
            yield division_uid, uids_in_division
        else:
            for stem, group in zip(stems, groups):
                yield stem, group


def get_matching_uids(divisions, text_uids, lang):
    """ yields uids belonging to the same division in proper order """
    text_uids = set(text_uids)
    
    for division_uid, uids in divisions:
        matches = tuple(uid for uid in uids if uid in text_uids)
        yield matches


def get_best_match(text, other_texts):
    author_uid = text['author_uid']
    for other_text in other_texts:
        if other_text['author_uid'] == author_uid:
            return other_text
    for other_text in other_texts:
        if other_text['segmented']:
            return other_text
    return sorted(other_texts, key=lambda t: t['author_uid'])[0] # TODO:Improve


def fix_mismatched_uids(texts, divisions):
    menu_uids = set(itertools.chain.from_iterable(t[1] for t in divisions))
    text_uids = set(text['uid'] for text in texts)
    
    mismatched_uids = text_uids.difference(menu_uids)
    print(f'{len(mismatched_uids)} texts have mismatched uids, attempting to match')
    uid_matcher = UidMatcher(all_uids=menu_uids)
    
    matches = {}
    
    for uid in sorted(mismatched_uids, key=numericsortkey):
        print(uid)
        matching_uids = uid_matcher.get_matching_uids(uid)
        print(f'Matches found for {uid}: {matching_uids}')
        if matching_uids:
            matches[uid] = matching_uids
    
    updates = {}
    for text in texts:
        uid = text['uid']
        if uid in matches:
            updates[text['_key']] = {'menu_uids': matches[uid]}
    
    return updates  
    

def update_collections(collection_docs_mapping, all_updates):
    for collection, texts in collection_docs_mapping:
            matching_keys = {text['_key'] for text in texts}
            updates = [{'_key': _key, **update} for _key, update in all_updates.items() if _key in matching_keys]
            collection.import_bulk(updates, on_duplicate="update")


def add_next_prev_using_menu_data(db):
    po_texts = list(db.aql.execute('''
        FOR doc IN po_strings
            RETURN {
                _key: doc._key,
                uid: doc.uid,
                lang: doc.lang,
                author_uid: doc.author_uid,
                name: doc.title,
                segmented: true
            }
    '''))
    
    html_texts = list(db.aql.execute('''
        FOR doc IN html_text
            RETURN {
                _key: doc._key,
                uid: doc.uid,
                lang: doc.lang,
                author_uid: doc.author_uid,
                name: doc.name,
                segmented: false
            }
    '''))
    
    
    texts = po_texts + html_texts
    
    divisions = [(doc['division'], tuple(doc['uids'])) for doc in db.aql.execute(UIDS_IN_ORDER_BY_DIVISION)]
    divisions = list(further_split_uids(divisions))
    
    mismatch_updates = fix_mismatched_uids(texts, divisions)
    
    update_collections([(db['po_strings'], po_texts), (db['html_text'], html_texts)], mismatch_updates)
    
    # First group texts by language
    for lang, lang_texts in sort_and_groupby(texts, lambda text: text['lang']):
        
        #Build a mapping of uids to translations of that uid in this lang
        mapping = defaultdict(dict)
        for text in lang_texts:
            uid = text['uid']
            author_uid = text['author_uid']
            mapping[uid][author_uid] = text
        
        collection_updates = defaultdict(dict)
        
        for matches in get_matching_uids(divisions=divisions, text_uids=set(mapping), lang=lang):
            # matches contains a list of uids in the same division in proper order
            for i, uid in enumerate(matches):
                for lang, text in mapping[uid].items():
                    if i > 0:
                        prev_uid = matches[i-1]
                        best_match = get_best_match(text, mapping[prev_uid].values())
                        
                        collection_updates[text['_key']].update({
                            'prev': {
                                'author_uid': best_match['author_uid'],
                                'lang': best_match['lang'],
                                'name': best_match['name'],
                                'uid': best_match['uid']
                            }
                        })
                    if i < len(matches) - 1:
                        next_uid = matches[i+1]
                        best_match = get_best_match(text, mapping[next_uid].values())
                        collection_updates[text['_key']].update({
                            'next': {
                                'author_uid': best_match['author_uid'],
                                'lang': best_match['lang'],
                                'name': best_match['name'],
                                'uid': best_match['uid']
                            }
                        })
    
        update_collections([(db['po_strings'], po_texts), (db['html_text'], html_texts)], collection_updates)


