# Finance-analyser
This is a personal finance analyser

if your bank statements are in pdf form you will first need to go to the bottom of the code for pdf-csv_converter and chnage pdf_path from "2026-03-27_Statement-1.pdf" to the name of your bank statement
then you will need to run the pdf-csv converter which will transform it to a csv called transactions.csv (this probably only works with HSBC bank statements, if your bank gives a pdf and it isn't hsbc you could also use tabula to transform the pdf to csv by selecting which part you want to convert)
now you just run the finance_analyser and it should give you statistics of your purchases and income and categorises it

if your bank statements are in csv you will either need to rename the file to "transactions.csv" or go into finance_analyser and at the bottom change csv_path from "transactions.csv" to the name of your csv file
