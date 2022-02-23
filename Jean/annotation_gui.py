import json
import copy
import jinja2
import random
import string
import PySimpleGUI as sg


"""
Templating system
"""
TEMPLATES = {
    'var1' : 'x',
    'var2' : 'y',
    'var3' : 'z',
    'lst1' : 'L',
    'lst2' : 'M',
    'lst3' : 'N',
    'mat1': 'A',
    'mat2': 'B',
    'mat3': 'C',
    'dict1': 'd1',
    'dict2': 'd2',
    'dict3': 'd3'
}

RND_GENERATORS = {
    'rnat'     : lambda : random.randint(0,100) ,
    'rint'     : lambda : random.randint(-100,100) ,
    'rfloat'   : lambda : (random.random()-0.5)*100 ,
    'rstring'  : lambda length : ''.join(random.choice(string.ascii_letters) for _ in range(length)) ,
    'rintlist' : lambda length : [ random.randint(-100,100) for _ in range(length) ]
}
    
def get_value(generator_name,param):
    """
    Generates a random template value from a generator name with its param
    """    
    if param:
        return RND_GENERATORS[generator_name](param)
    else:
        return RND_GENERATORS[generator_name]()

    
def parse_generator_expr(expr):
    #   format : @RINTLIST_3 or @RNAT
    assert(expr.startswith('@'))
    if '_' in expr:
        (name,param) = expr.split('_')
        return (name,param)
    else:
        return (expr,None)

def parse_template_expr(expr):
    # ex. format 'mylist =  @RINTLIST_3'
    assert('=' in expr)
    (template,generator) = expr.split('=')
    return template.strip(), parse_generator_expr(generator.strip())



class AbstractItem(object):
    
    #Item with templates (to be evaluated)
    def __init__(self,idx,intent,code,tests,pkg,labels,rnd_generators):
        self.idx            = idx       #int
        self._intent        = intent    #str
        self._code          = code      # str
        self._tests         = tests     #list of tests (couple of str : args,assertion)
        self._pkg           = pkg
        self._labels        = labels
        self._rnd_templates = rnd_generators                 #list of couples ('template name', @GEN_STRING)
        self._templates = self._sample_templates_dict()  #list of couples ('template name', GEN_STRING)


    @property
    def pkg(self):
        return self._pkg
    
    @property
    def labels(self):
        return self._labels

    def __setattr__(self, name, value):
        #allows to set the following attributes without underscore
        if name in ['pkg','labels','intent','code','tests','rnd_templates']:
            self.__setattr__('_'+name,value)
        else:
            super(AbstractItem, self).__setattr__(name, value)
  
    def clone(self):
        return copy.deepcopy(self)
    
    def sample(self):
        cpy = copy.deepcopy(self)
        cpy._templates =  self.sample_templates_dict()
        return cpy
        
    def _sample_templates_dict(self):
        return dict ( (name,get_value(*parse_generator_expr(expr))) for name,generator in self._rnd_templates)
        
    @staticmethod
    def create_empty(idx):
        return AbstractItem(idx,'','',[ ],[ ],[ ],[ ])
    
    @staticmethod
    def from_json(item):
        
        def fix_format(tests):
            return [(T['input'],T['asserts'][0]) for T in tests]
            
        return AbstractItem(item['question_id'],item['intent'],item['code'],item['tests cases'],item['package'],item['labels'],item['templates'] if 'templates' in item else [])

    
    def to_json(self,eval_tpl):
        return json.dumps({'question_id' : self.idx,
                           "intent": self.intent(eval_tpl),
                           'package':self._pkg,
                           'tests cases' : self.tests(eval_tpl) ,
                           'labels':self._labels,
                           "code" : self.code(eval_tpl),
                           'templates':self._rnd_templates})
    def __str__(self):
        return self.to_json(False)
    
    def intent(self,eval_tpl=False):
        if eval_tpl:
            return self._render(self._intent)
        else:
            return self._intent
        
    def code(self,eval_tpl=False):
        if eval_tpl:
            return self._render(self._code)
        else:
            return self._code

    def tests(self,eval_tpl=False):
        if eval_tpl:
            return [( self._render(arg),self._render(assertion) ) for (arg,assertion) in self._tests]
        else:
            return self._tests
        
    def _render(self,expr):
        """
        evaluates the templates in expr given their definitions
        """
        return jinja2.Template(expr,undefined=jinja2.StrictUndefined).render(TEMPLATES | self._templates)

    def full_item_code(self,eval_tpl=True):
        """
        Runs the tests for this item and returns (num success,num tests performed)
        """
        local_tpl = {
            'imports' : self._pkg,
            'func'    : self.code(eval_tpl  = eval_tpl),
            'tests'   : self.tests(eval_tpl = eval_tpl)
        }

        test_code = """{%- for imp in imports %}
import {{ imp }}
{%- endfor %}
{% for imp in imports %}
global {{ imp }}
{%- endfor %}
global foo

{{func}}  

bool_results = [ ]
{% for T in tests %}
__result__ = foo(*{{ T[0] }} )
bool_results.append( {{ T[1] }})
{%- endfor %}
"""
        test_code = jinja2.Template(test_code).render(local_tpl,trim_blocks = True)
        return test_code

    def run_test(self):
        test_code = self.full_item_code()
        #print('\n----------------------------\n'+self.intent(eval_tpl=True))
        #print(test_code)
        results = [ ]
        ldic    = locals()
        exec(test_code)
        results = ldic['bool_results']
        return sum(results),len(results)
        
    
################################################
def load_data(filename,reindex=True):
    
    istream = open(filename)
    try:
        dataset = json.load(istream)
    except ValueError as e:
        print('**json parser error**')
        raise SystemExit(e)
    
    dataset = [AbstractItem.from_json(item) for item in dataset['data']]

    #reindex items
    if reindex:
        for idx, item in enumerate(dataset):
            item.idx = idx

    
    istream.close()
    return dataset

def load_pkg(filename):
    istream = open(filename)
    dataset = json.load(istream)
    istream.close()
    return dataset['packages']


def load_labels(filename):
    istream = open(filename)
    dataset = json.load(istream)
    istream.close()
    return dataset['labels']
    
def save_data(filename,dataset,pkg,labels):

    ostream = open(filename,'w')
    ostream.write('{\n')
    ostream.write('"packages" : %s,\n'%json.dumps(pkg))
    ostream.write('"labels" : %s,\n'%json.dumps(labels))
    ostream.write('"data" : [')
    ostream.write(',\n'.join(item.to_json(eval_tpl=False) for item in dataset))
    ostream.write(']\n}')
    ostream.close()

    
def check_dataset(dataset):
    for item in dataset:
        try :
            print(item.run_tests(item.code))
        except Exception as e:
            print(e)

            
class TestFailedException(Exception):

    def __init__(self,msg):
        super(TestFailedException).__init__()
        self.msg = msg

    def __str__(self):
        return self.msg



class DatasetGUI:

    def __init__(self,jsonfilename):
        
        self.filename = jsonfilename
        self.data     = load_data(self.filename)
        self.pkg_list = load_pkg(self.filename)
        self.lbl_list = load_labels(self.filename)

        
    def show(self,idx=0):
        
        WIDTH  = 80
        HEIGHT = 10
        
        titlefont = ("Arial", 36)
        codefont  = ("Courier",24)
        listfont  = ("Arial",24) 
        deffont   = ("Arial",14) 
        
        ListColumn = sg.Column([[ sg.Text('Exercises',font=titlefont)],
                                [sg.Listbox(["Exercise %d"%(item.idx)  for item in self.data],size=(10,24),
                                                font=listfont,
                                                enable_events=True,
                                                select_mode="LISTBOX_SELECT_MODE_SINGLE" ,
                                                default_values = ['Exercise 0'],
                                                key='--ITEM--')],
                                 [sg.VPush()],
                                 [sg.Submit("New",font=deffont,key='--ADD--'),sg.Submit("Clone",font=deffont,key='--CLONE--')]],
                                 element_justification='c' )
                       
        ExColumn  =  sg.Column([[sg.Text("Intent",font=titlefont)],
                                 [sg.Multiline('',size=(WIDTH,HEIGHT-5),font=codefont,key="--INTENT--") ],
                                 [sg.Text("Code",font=titlefont),sg.Text(font=listfont,key="--SEL_PKG--"),sg.VerticalSeparator(),sg.Text(font=listfont,key="--SEL_LBL--"),sg.Push(),
                                      sg.Submit("Add package",font=deffont,key="--PKG--"),
                                      sg.Submit("Clear packages",font=deffont,key="--rmPKG--"),
                                      sg.Submit("Add flag",font=deffont,key='--LBL--'),
                                      sg.Submit("Clear flags",font=deffont,key='--rmLBL--'),
                                 ],
                                 [sg.Multiline('',size=(WIDTH,HEIGHT),font=codefont,key="--CODE--") ],
                                 [sg.Text("Tests",font=titlefont)],
                                 [sg.Text('Arguments',font=deffont,size=(52,1)), sg.Text('Assertions',font=deffont,size=(10,1))],
                                 [sg.Multiline(size=(50,10),font=deffont,key="--ARGS--"),sg.Multiline(size=(30,10),font=deffont,key="--ASSERTS--",expand_x=True)],
                                 [sg.Push(),sg.Submit("Check Item",font=deffont,key='--CHECK--')]
                                 ],
                                 element_justification='l')


        layout = [[ListColumn,ExColumn]]    

        window = sg.Window('Python exercises Editor', layout,enable_close_attempted_event=True,finalize=True)    

        def fill_exercise(sel_idx):

            window['--INTENT--'].update(self.data[sel_idx].intent())
            window['--CODE--'].update(self.data[sel_idx].code())
            if self.data[sel_idx].pkg:
                window['--SEL_PKG--'].update(','.join(self.data[sel_idx].pkg))
            else:
                window['--SEL_PKG--'].update('')
            if self.data[sel_idx].labels:
                window['--SEL_LBL--'].update(','.join(self.data[sel_idx].labels))
            else:
                window['--SEL_LBL--'].update('')
            args  = [ ]
            tests = [ ]
            argslist = '\n'.join( args for args,assertion in self.data[sel_idx].tests( ) )
            asstlist = '\n'.join( assertion for args,assertion in self.data[sel_idx].tests( ) )                
              
            window['--ARGS--'].update(argslist)
            window['--ASSERTS--'].update(asstlist)


        def add_item(new_item):
            midx = max(item.idx for item in self.data)
            new_item.idx = midx+1
            self.data.append(new_item)
            fill_exercise(midx+1)
            vals = window['--ITEM--'].get_list_values()
            vals.append('Exercise %d'%(midx+1))
            window['--ITEM--'].update(values=vals,set_to_index=[midx+1], scroll_to_index=midx+1)
            return midx+1

        
        def color_items(sel_idx = None):
            
            red   = '#FC566E'
            green = '#7BCE64'
            malformed  = []
            wellformed = []

            for idx,item in enumerate(self.data):
                if sel_idx and sel_idx != idx:
                    continue
                
                try:
                    self.data[idx].intent(eval_tpl=True) # checks if the intent is well templated
                    succ,n = self.data[idx].run_test()
                    if succ == n:
                        wellformed.append(idx)
                    else:
                        malformed.append(idx)
                except Exception as e:
                    print(e)
                    malformed.append(idx)

                    
            listbox = window['--ITEM--']
            for idx in malformed:
                listbox.Widget.itemconfigure(idx, bg=red, fg='white')

            for idx in wellformed:
                listbox.Widget.itemconfigure(idx, bg=green, fg='white')

                
        def update_item(sel_idx):
                                
            item        = self.data[sel_idx]
            item.intent =  window['--INTENT--'].get()          
            item.code   =  window['--CODE--'].get()
            pkg_lst     =  window['--SEL_PKG--'].get().split(',')
            item.pkg    =  pkg_lst if pkg_lst != [''] else []
            lbl_lst     =  window['--SEL_LBL--'].get().split(',')
            item.labels =  lbl_lst if lbl_lst != [''] else []
            args_str    =  window['--ARGS--'].get().split('\n')
            assert_str  =  window['--ASSERTS--'].get().split('\n')

            if args_str == ['']: #args are empty
                args_str = []
            if len(args_str) < len(assert_str): #add missing empty args
                args_str = args_str + ['[ ]']* (len(assert_str) -  len(args_str))
                
            item.tests = list(zip(args_str,assert_str))


        def get_selected(values):
            return  int(values['--ITEM--'][0].split(' ')[1])

        def popup_code(intent,code_str,err_message=''):
            lines = code_str.split('\n')
            code_str = '\n'.join('%s: %s'%(str(idx+1).ljust(2),line) for idx,line in enumerate(lines))
            layout = [
                [sg.Multiline(intent,font=codefont,size=(WIDTH,4),disabled=True,no_scrollbar = True,text_color='black',background_color ='#F8FBEF')],
                [sg.Multiline(code_str,size=(WIDTH,HEIGHT*2),disabled=True,font=codefont,text_color='black',background_color ='#F8FBEF')],
                [sg.StatusBar(err_message,text_color='#F6CECE',font=listfont,visible= (err_message != ''))],
                [sg.Button('OK',font=listfont)]]
                
            window = sg.Window('Check results' , layout,modal=True,keep_on_top=True).Finalize()
            while True:
                event, values = window.read()
                if event == sg.WINDOW_CLOSED:
                  break
                elif event == 'OK':
                  break
            window.close()

                  
        def popup_list(text, list_data):
            layout = [
            [sg.Text(text,font=deffont)],
            [sg.Listbox(list_data,size=(15,10),select_mode="LISTBOX_SELECT_MODE_MULTIPLE",font=deffont, key='--LIST--',expand_x=True)],
            [sg.Button('OK'),sg.Button('+'),sg.Input('',key='--NEW--',visible=False,expand_x=True)],]
    
            window = sg.Window('POPUP', layout).Finalize()
            window['--NEW--'].bind("<Return>", "--ENT--")
            while True:
                event, values = window.read()
                if event == sg.WINDOW_CLOSED:
                    break
                elif event == '+':
                    window['--NEW--'].update(visible=True)
                elif event == '--NEW--'+'--ENT--' or (event == 'OK' and  window['--NEW--'].get()) :
                    newcat = window['--NEW--'].get()
                    list_data.append(newcat)
                    window['--LIST--'].update(values=list_data)
                    window['--NEW--'].update(value='',visible=False)
                elif event == 'OK':
                    break
                    
            window.close()

            if values and values['--LIST--']:
                return values['--LIST--']
            

        #main loop
        fill_exercise(0)
        color_items()
        prev_idx = 0
        while True:
            
            event, values = window.read()

            if event == sg.WINDOW_CLOSE_ATTEMPTED_EVENT or event == 'Exit':
                update_item(prev_idx)            
                save_data(self.filename,self.data,self.pkg_list,self.lbl_list)
                break         
            
            sel_idx   = get_selected(values)
            
            if event == '--ITEM--':
                update_item(prev_idx)
                color_items(prev_idx)
                save_data(self.filename,self.data,self.pkg_list,self.lbl_list)
                fill_exercise(sel_idx)
                
            elif event == '--CHECK--':
                
                update_item(sel_idx)
                try:
                    self.data[sel_idx].intent(eval_tpl=True) # checks if the intent is well templated
                    nsucc,ntests = self.data[sel_idx].run_test()
                    if nsucc < ntests:
                        raise TestFailedException('Tests failed: %d successes out of %d attempts'%(nsucc,ntests))
                    popup_code(self.data[sel_idx].intent(eval_tpl=True),self.data[sel_idx].full_item_code(),err_message='Item is correct')
                except TestFailedException as e:
                    popup_code(self.data[sel_idx].intent(eval_tpl=True),self.data[sel_idx].full_item_code(eval_tpl=False),err_message='Fails to pass the test: ' +str(e))
                except (jinja2.exceptions.UndefinedError,jinja2.exceptions.TemplateSyntaxError) as e:
                    popup_code(self.data[sel_idx].intent(eval_tpl=False),self.data[sel_idx].full_item_code(eval_tpl=False),err_message='Undefined template: ' +str(e))
                #except (SyntaxError,TypeError,NameError,ZeroDivisionError,RuntimeError,ValueError) as e:
                except Exception as e:
                    popup_code(self.data[sel_idx].intent(eval_tpl=True),self.data[sel_idx].full_item_code(eval_tpl=False),err_message='Code does not evaluate: ' +str(e))                
                
                color_items(sel_idx)
                
            elif event == "--PKG--":
                result = popup_list('Select required packages', list_data=self.pkg_list)
                pkg    = window['--SEL_PKG--'].get().split(',')
                if result:
                    if pkg[0]:
                       result += pkg
                    window['--SEL_PKG--'].update(','.join(sorted(set(result))))
                    update_item(sel_idx)

            elif event == "--rmPKG--":
                 window['--SEL_PKG--'].update('')
                 update_item(sel_idx)            

            elif event == "--LBL--":
                result = popup_list('Select label', list_data=self.lbl_list)
                lbl    = window['--SEL_LBL--'].get().split(',')
                if result:
                    if lbl[0]:
                        result += lbl
                    window['--SEL_LBL--'].update(','.join(sorted(set(result))))
                    update_item(sel_idx)

            elif event == "--rmLBL--":
                 window['--SEL_LBL--'].update('')
                 update_item(sel_idx)            
        
            elif event == '--ADD--':
                save_data(self.filename,self.data,self.pkg_list,self.lbl_list)
                sel_idx = add_item(AbstractItem.create_empty(-1))
                color_items()

            elif event == '--CLONE--':
                save_data(self.filename,self.data,self.pkg_list,self.lbl_list)
                sel_idx = add_item(self.data[sel_idx].clone())
                color_items()
            
            prev_idx = sel_idx
                 
        window.close()
        save_data(self.filename,self.data,self.pkg_list,self.lbl_list)
    
        
if __name__ == '__main__':
    import sys
    
    gui = DatasetGUI(sys.argv[1])
    gui.show()




        
