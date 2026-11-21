from datetime import datetime
SEED = [
("What is the output of print(2 + 3)?", "4", "5", "23", "Error", "b", "Python evaluates the addition and prints 5."),
("Which data type is used to store text in Python?", "int", "float", "str", "bool", "c", "Text is stored as str (string)."),
("What does an if statement do?", "Repeats code forever", "Runs code only when a condition is True", "Defines a function", "Imports a module", "b", "An if block executes only when its condition is True."),
("What is the purpose of a for loop?", "To iterate over a sequence", "To define a variable", "To stop the program", "To print text", "a", "A for loop repeats a block for each item in a sequence."),
("Which statement repeats code while a condition remains True?", "for", "if", "while", "def", "c", "while keeps looping as long as its condition is True."),
("How do you define a function in Python?", "function f():", "def f():", "func f():", "define f():", "b", "Functions are defined with the def keyword."),
("What does len([10, 20, 30]) return?", "2", "3", "30", "60", "b", "len() returns the number of items: 3."),
("Which symbol is used for equality comparison?", "=", "==", "!=", "=>", "b", "== compares values; = assigns a value."),
("How can a list be created?", "x = (1, 2)", "x = {1, 2}", "x = [1, 2]", "x = <1, 2>", "c", "Lists use square brackets."),
("What is the purpose of break inside a loop?", "Skip one iteration", "Exit the loop immediately", "Restart the loop", "Pause the program", "b", "break ends the loop immediately; continue skips one iteration."),
]
def seed(db):
    if db.execute("SELECT 1 FROM assessments LIMIT 1").fetchone(): return
    c = db.execute("""INSERT INTO assessments(title,subject,description,duration,total_questions,marks_per_question,passing_score,
      instructions,access_code,camera_monitoring,nav_monitoring,warning_limit,auto_submit,show_answers,phone_terminate,published,created_at)
      VALUES('Python Programming Fundamentals','Python','Beginner Python MCQ covering variables, types, control flow, functions, lists and strings.',
      20,10,1,40,'Answer all 10 questions. Each correct answer is 1 mark. No negative marking.','',1,1,2,1,1,0,1,?)""", (datetime.now().isoformat(),))
    for i, q in enumerate(SEED, 1):
        db.execute("INSERT INTO questions(assessment_id,position,text,a,b,c,d,correct,explanation,marks) VALUES(?,?,?,?,?,?,?,?,?,1)", (c.lastrowid, i, *q))
    db.commit()
